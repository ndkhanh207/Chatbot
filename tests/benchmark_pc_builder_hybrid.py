"""Run manually with local embeddings and Ollama: python tests/benchmark_pc_builder_hybrid.py"""

from __future__ import annotations

import asyncio
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import (
    BuildQuery,
    ChromaSemanticIndex,
    ShopCatalog,
    create_embeddings,
)
from app.catalog.models import BuildConstraints
from app.catalog.catalog import normalize
from app.pc_builder import reranker
from config.config import Config


@dataclass(frozen=True)
class Case:
    name: str
    query: BuildQuery
    expected_purpose_codes: tuple[str, ...] = ()
    expected_action: str = "select"
    requirements: tuple[str, ...] = ()
    clarification_count: int = 0
    force_select: bool = False


CASES = [
    Case("gaming-20m", BuildQuery(text="gaming 2K cân bằng", budget=20_000_000, limit=5)),
    Case("office-15m", BuildQuery(text="văn phòng Word Excel", budget=15_000_000, limit=5), ("OFF-01",)),
    Case("render-30m", BuildQuery(text="render video đồ họa", budget=30_000_000, limit=5), ("CRE-02", "CRE-03", "CRE-06")),
    Case("ai-50m", BuildQuery(text="AI machine learning", budget=50_000_000, limit=5), ("AI-01", "AI-02", "AI-03", "AI-04", "AI-05")),
    Case("programming-20m", BuildQuery(text="lập trình Docker máy ảo dữ liệu nặng", budget=20_000_000, limit=5), ("OFF-04", "WS-01")),
    Case("esport-15m", BuildQuery(text="esport FPS 144Hz", budget=15_000_000, limit=5), ("GAME-02", "GAME-06")),
    Case("aaa-40m", BuildQuery(text="game AAA độ phân giải cao", budget=40_000_000, limit=5), ("GAME-04", "GAME-05", "GAME-07", "GAME-08")),
    Case("budget-10m", BuildQuery(text="phổ thông", budget=10_000_000, limit=5), expected_action="clarify"),
    Case("budget-25m", BuildQuery(text="cân bằng", budget=25_000_000, limit=5), expected_action="clarify"),
    Case("intel", BuildQuery(text="gaming", budget=30_000_000, constraints=BuildConstraints(preferred_components={"cpu": ["Intel"]}), limit=5)),
    Case("amd", BuildQuery(text="gaming", budget=30_000_000, constraints=BuildConstraints(preferred_components={"cpu": ["AMD"]}), limit=5)),
    Case("upgrade-cpu", BuildQuery(text="nâng cấp phần còn lại", constraints=BuildConstraints(required_components={"cpu": "Ryzen 7 7700X"}), limit=5)),
    Case("upgrade-gpu", BuildQuery(text="nâng cấp phần còn lại", constraints=BuildConstraints(required_components={"gpu": "RTX 4080"}), limit=5)),
    Case("mainboard-filter", BuildQuery(text="gaming", constraints=BuildConstraints(required_components={"mainboard": "B850"}), limit=5)),
    Case("exclude-old", BuildQuery(text="gaming", budget=25_000_000, excluded_ids={"BUILD-06265"}, limit=5)),
    Case("brand-gpu", BuildQuery(text="gaming", budget=30_000_000, constraints=BuildConstraints(preferred_components={"gpu": ["NVIDIA"]}), limit=5)),
    Case(
        "vague-build",
        BuildQuery(text="build pc", limit=5),
        expected_action="clarify",
        requirements=("build pc",),
    ),
    Case(
        "vague-strong",
        BuildQuery(text="máy mạnh", limit=5),
        expected_action="clarify",
        requirements=("mình cần máy mạnh",),
    ),
    Case(
        "forced-after-two",
        BuildQuery(text="game AAA", limit=5),
        requirements=("build pc", "chủ yếu chơi game", "ưu tiên game AAA"),
        clarification_count=2,
        force_select=True,
    ),
    Case("cheapest", BuildQuery(price_order="asc", limit=1)),
    Case("expensive", BuildQuery(price_order="desc", limit=1)),
]


def load_catalog() -> ShopCatalog:
    embeddings = create_embeddings()
    embeddings.embed_query("test")
    return ShopCatalog.load(
        Config.PC_STORE_DATA,
        semantic_index=ChromaSemanticIndex(Config.VECTOR_DB_DIR, embeddings),
        embedding_config=(
            f"model={Config.EMBEDDING_MODEL};device={Config.EMBEDDING_DEVICE};"
            "batch=8;metric=cosine"
        ),
    )


def satisfies(query: BuildQuery, candidate) -> bool:
    if query.budget is not None and candidate.total_price > query.budget:
        return False
    if candidate.build_id.casefold() in {value.casefold() for value in query.excluded_ids}:
        return False
    for category, model in query.constraints.required_components.items():
        key = "mainboard" if category.casefold() in {"main", "motherboard"} else category.casefold()
        if key not in candidate.components or normalize(model) not in normalize(candidate.components[key].model):
            return False
    for category, brands in query.constraints.preferred_components.items():
        for brand in brands:
            wanted = normalize(brand)
            if category.casefold() == "any":
                if not any(wanted in normalize(part.brand) for part in candidate.components.values()):
                    return False
            elif wanted not in normalize(candidate.components[category.casefold()].brand):
                return False
    return True


async def run() -> None:
    catalog = load_catalog()
    original_invoke = reranker._invoke_model
    original_fallback = reranker._fallback
    model_calls = 0
    fallbacks = 0

    async def counted_invoke(request, candidates):
        nonlocal model_calls
        model_calls += 1
        return await original_invoke(request, candidates)

    def counted_fallback(candidates):
        nonlocal fallbacks
        fallbacks += 1
        return original_fallback(candidates)

    reranker._invoke_model = counted_invoke
    reranker._fallback = counted_fallback
    reranker._decision_cache.clear()
    rows = []
    retrieval_hits = []
    try:
        for case in CASES:
            print(f"Running {case.name}", flush=True)
            started = perf_counter()
            candidates = catalog.search_builds(case.query)
            baseline_ms = (perf_counter() - started) * 1000
            hard_valid = all(satisfies(case.query, candidate) for candidate in candidates)
            if case.expected_purpose_codes:
                retrieval_hits.append(any(
                    candidate.attributes.get("Purpose_Code") in case.expected_purpose_codes
                    for candidate in candidates
                ))
            if not candidates:
                rows.append((
                    case.name, "N/A", "N/A", hard_valid, False, False,
                    0, baseline_ms, baseline_ms,
                ))
                continue

            baseline_id = candidates[0].build_id
            before_calls = model_calls
            hybrid_started = perf_counter()
            decision = await reranker.choose_build({
                "requirements": list(case.requirements or (case.query.text,)),
                "budget": case.query.budget,
                "components": case.query.constraints.required_components,
                "mandatory_brands": {k: v[0] for k, v in case.query.constraints.preferred_components.items()} if case.query.constraints.preferred_components else {},
                "quantity": 1,
                "clarification_count": case.clarification_count,
                "force_select": case.force_select or bool(case.query.price_order),
                "response_mode": None,
                "response_facts": {},
                "selection_facts": {
                    candidate.build_id: {
                        "quantity": None,
                        "total_for_quantity": None,
                    }
                    for candidate in candidates
                },
            }, candidates)
            action = decision.action
            result = decision.selected_build_id or "CLARIFY"
            selected_valid = (
                action == "clarify"
                or result.casefold() in {candidate.build_id.casefold() for candidate in candidates}
            )
            hybrid_ms = baseline_ms + (perf_counter() - hybrid_started) * 1000
            rows.append((
                case.name,
                baseline_id,
                result,
                hard_valid,
                action == case.expected_action,
                selected_valid,
                model_calls - before_calls,
                baseline_ms,
                hybrid_ms,
            ))
    finally:
        reranker._invoke_model = original_invoke
        reranker._fallback = original_fallback

    baseline_latencies = [row[7] for row in rows]
    hybrid_latencies = [row[8] for row in rows]
    baseline_p95 = sorted(baseline_latencies)[max(0, math.ceil(len(rows) * 0.95) - 1)]
    hybrid_p95 = sorted(hybrid_latencies)[max(0, math.ceil(len(rows) * 0.95) - 1)]
    hard_accuracy = sum(row[3] for row in rows) / len(rows) * 100
    action_accuracy = sum(row[4] for row in rows) / len(rows) * 100
    selection_accuracy = sum(row[5] for row in rows) / len(rows) * 100
    recall_at_five = sum(retrieval_hits) / len(retrieval_hits) * 100
    lines = [
        "# PC Builder Retrieval vs Adaptive Decision Benchmark",
        "",
        f"- Hard-constraint compliance: {hard_accuracy:.1f}%",
        f"- Expected-purpose-code Recall@5: {recall_at_five:.1f}%",
        f"- Expected-action accuracy: {action_accuracy:.1f}%",
        f"- Candidate-selection validity: {selection_accuracy:.1f}%",
        f"- Model calls: {sum(row[6] for row in rows)}",
        f"- Deterministic fallbacks: {fallbacks}",
        f"- Retrieval median/p95 latency: {statistics.median(baseline_latencies):.1f}/{baseline_p95:.1f} ms",
        f"- Adaptive median/p95 latency: {statistics.median(hybrid_latencies):.1f}/{hybrid_p95:.1f} ms",
        "",
        "| Case | Retrieved Top-1 | Decision | Hard-valid | Action-valid | Selection-valid | Calls | Retrieval ms | Adaptive ms |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {name} | {baseline} | {decision} | {'yes' if hard_valid else 'no'} | "
        f"{'yes' if action_valid else 'no'} | {'yes' if selection_valid else 'no'} | "
        f"{calls} | {base_ms:.1f} | {hybrid_ms:.1f} |"
        for name, baseline, decision, hard_valid, action_valid, selection_valid, calls, base_ms, hybrid_ms in rows
    )
    report = Path("tests/reports/report_pc_builder_hybrid_benchmark.md")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {report}")

    assert hard_accuracy == 100.0
    assert recall_at_five >= 80.0
    assert fallbacks == 0
    assert action_accuracy == 100.0
    assert selection_accuracy == 100.0


if __name__ == "__main__":
    asyncio.run(run())
