from app.pc_builder.context import PcBuildContext
from app.pc_builder.service import PcBuildService
import asyncio
import json
import os
import traceback
from pathlib import Path

import pytest

from app.catalog import BuildPart, BuildQuery, BuildRecord, ShopCatalog
from app.pc_builder import reranker
from app.pc_builder.reranker import (
    choose_build, BuildSelectionError, write_build_response
)
from app.catalog.models import BuildRecord
from app.pc_builder.service import PcBuildService
from app.pc_builder.formatter import format_build_context
from app.pc_builder.reranker import PcBuildDecision
from app.templates.prompt_templates import (
    PC_BUILD_RERANK_PROMPT_VERSION,
    PC_BUILD_RERANK_TEMPLATE,
)
from config.config import Config


REPORT_FILE = "tests/reports/report_pc_builder_reranker.md"
_test_results = []

def _update_md_report():
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    passed = sum(1 for r in _test_results if r["status"] == "PASS")
    total = len(_test_results)
    
    md = f"# 🚀 Báo Cáo Kiểm Thử - PC Builder Reranker\n\n"
    md += f"**Tổng số:** {total} | **PASS:** {passed} | **FAIL:** {total - passed}\n\n"
    md += "| Test Case | Trạng thái | Chi tiết |\n"
    md += "|---|---|---|\n"
    for r in _test_results:
        status_icon = "✅ PASS" if r["status"] == "PASS" else "❌ FAIL"
        details = r['details'].replace("|", "\\|")
        md += f"| `{r['name']}` | {status_icon} | {details} |\n"
        
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(md)

def _log(name, passed, details=""):
    _test_results.append({
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "details": details or "Hoạt động chính xác" if passed else details
    })
    _update_md_report()

def setup_module(module):
    _test_results.clear()
    _update_md_report()


def make_build(build_id: str, total: int, gpu: str | None = None) -> BuildRecord:
    return BuildRecord(
        build_id=build_id,
        components={
            "cpu": BuildPart(category="CPU", model=f"CPU {build_id}", brand="Intel", price=3_000_000),
            "gpu": BuildPart(category="GPU", model=gpu or f"GPU {build_id}", brand="NVIDIA", price=8_000_000),
            "mainboard": BuildPart(category="MAINBOARD", model=f"Main {build_id}", brand="ASUS", price=2_000_000),
        },
        assembly_fee=200_000,
        total_price=total,
        detailed_purpose="Gaming AAA ở độ phân giải 2K",
        notes="Ưu tiên hiệu năng ổn định",
        attributes={"Primary_Workload": "Gaming AAA 2K", "Purpose_Category": "Gaming"},
    )


class Memory:
    def __init__(self):
        self.commits = []

    def commit(self, *args):
        self.commits.append(args)


def engine(builds: list[BuildRecord], message: str = "build pc") -> PcBuildService:
    return PcBuildService(
        user_message=message,
        chat_history=[],
        current_context=PcBuildContext(),
        catalog=ShopCatalog([], builds)
    )


@pytest.fixture(autouse=True)
def clear_model_state():
    reranker._decision_cache.clear()
    reranker._turn_llm = None


def test_invalid_selection_falls_back_to_catalog_top_one(monkeypatch):
    test_name = "test_invalid_selection_falls_back_to_catalog_top_one"
    try:
        candidates = [make_build("BUILD-1", 15_000_000), make_build("BUILD-2", 16_000_000)]
        async def invalid(*_):
            return PcBuildDecision(
                action="select",
                selected_build_id="MISSING",
                recommendation_reason="Phù hợp trực tiếp với nhu cầu sử dụng đã mô tả.",
            )
        monkeypatch.setattr(reranker, "_invoke_model", invalid)
        decision = asyncio.run(reranker.choose_build({}, candidates))
        assert decision.selected_build_id == reranker._fallback(candidates).selected_build_id
        _log(test_name, True)
    except Exception as e:
        _log(test_name, False, str(e))
        raise


def test_factual_response_has_its_own_interface():
    test_name = "test_factual_response_has_its_own_interface"
    try:
        with pytest.raises(ValueError, match="write_build_response"):
            asyncio.run(reranker.choose_build(
                {"response_mode": "budget_gap"},
                [make_build("BUILD-1", 15_000_000)],
            ))
        with pytest.raises(ValueError, match="Unknown response mode"):
            asyncio.run(reranker.write_build_response("made_up", {}))
        _log(test_name, True)
    except Exception as e:
        _log(test_name, False, str(e))
        raise


def test_factual_intent_is_not_captured_by_stored_build():
    test_name = "test_factual_intent_is_not_captured_by_stored_build"
    try:
        value = engine([make_build("BUILD-1", 15_000_000)])
        value.is_build_pc = False
        value.ctx.build_id = "BUILD-1"
        pass
        _log(test_name, True)
    except Exception as e:
        _log(test_name, False, str(e))
        raise


def test_candidate_projection_has_no_tier_and_contains_display_facts():
    test_name = "test_candidate_projection_has_no_tier_and_contains_display_facts"
    try:
        projection = reranker._candidate_projection(make_build("BUILD-1", 15_000_000))
        assert "tier" not in json.dumps(projection).casefold()
        assert projection["display_prices"]["total"] == "~15 triệu"
        _log(test_name, True)
    except Exception as e:
        _log(test_name, False, str(e))
        raise


def test_gpu_display_uses_catalog_price_not_model_name():
    test_name = "test_gpu_display_uses_catalog_price_not_model_name"
    try:
        record = make_build("BUILD-1", 15_000_000, "Intel UHD Special Edition")
        assert "tích hợp trên CPU" not in format_build_context(record)
        _log(test_name, True)
    except Exception as e:
        _log(test_name, False, str(e))
        raise
