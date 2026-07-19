"""Generate exact production PC Builder decision and state-update examples."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.catalog import BuildQuery, ShopCatalog
from app.pc_builder.context import PcBuildContext
from app.pc_builder.formatter import format_approx_million, format_build_context
from app.pc_builder.reranker import (
    PcBuildDecision,
    PcBuildTurnPlan,
    _candidate_projection,
    _validate_decision,
    _validate_response,
    _validate_turn_plan,
)
from app.templates.prompt_templates import (
    PC_BUILD_RERANK_TEMPLATE,
    PC_BUILD_TURN_TEMPLATE,
)

CATALOG_DIR = ROOT / "data" / "dataset"
OUTPUT = Path(__file__).with_name("pc_builder_adaptive.jsonl")
SEED = 3407

VAGUE_REQUIREMENTS = (
    "build pc cho mình",
    "mình cần một bộ máy mạnh",
    "tư vấn máy tính để bàn",
    "chọn giúp mình một cấu hình",
    "mình muốn mua máy mới",
    "cần một bộ PC ổn",
    "tư vấn dàn máy phù hợp",
    "mình cần máy để dùng lâu dài",
    "chọn một bộ PC tốt",
    "mình muốn ráp máy",
)

VAGUE_GAMING_REQUIREMENTS = (
    "tư vấn bộ pc chơi game",
    "build pc gaming cho mình",
    "mình cần máy để chơi game",
    "chọn giúp mình một bộ pc gaming",
    "ráp máy chơi game",
    "cần cấu hình gaming tốt",
    "mình muốn mua máy gaming",
    "tư vấn dàn máy để chơi game",
    "build bộ máy chuyên gaming",
    "chọn pc chơi game giúp mình",
)

GAMING_CLARIFICATION_QUESTIONS = (
    "Bạn chủ yếu chơi eSports, game AAA hay kết hợp cả hai?",
    "Bạn ưu tiên tốc độ khung hình cao hay chất lượng hình ảnh?",
    "Những trò chơi bạn sử dụng thường xuyên nhất là gì?",
    "Bạn muốn tối ưu cho thi đấu eSports hay trải nghiệm game nặng?",
    "Bạn ưu tiên chơi game ở độ phân giải hay độ mượt như thế nào?",
    "Bạn thường chơi thể loại game nào và mong muốn chất lượng hình ảnh ra sao?",
    "Nhu cầu gaming chính của bạn là eSports, AAA hay phát trực tiếp khi chơi?",
    "Bạn cần máy tập trung vào game cạnh tranh hay game có đồ họa nặng?",
    "Mục tiêu gaming quan trọng nhất của bạn là độ mượt hay chất lượng hình ảnh?",
    "Bạn dự định chơi game nào nhiều nhất trên bộ máy này?",
)

CLARIFICATION_QUESTIONS = (
    "Bạn sẽ dùng máy chủ yếu cho công việc hoặc hình thức giải trí cụ thể nào?",
    "Phần mềm hoặc trò chơi chính bạn dự định sử dụng là gì?",
    "Khối lượng công việc thường ngày của bạn nặng đến mức nào?",
    "Bạn cần ưu tiên tốc độ xử lý, hình ảnh hay chạy nhiều tác vụ?",
    "Mục tiêu sử dụng quan trọng nhất của bộ máy là gì?",
    "Bạn thường chạy công việc nào lâu hoặc thường xuyên nhất?",
    "Bạn cần máy đáp ứng phần mềm hay loại tác vụ cụ thể nào?",
    "Mức tải thực tế bạn dự định chạy trên máy là nhẹ, vừa hay nặng?",
    "Bạn muốn tối ưu bộ máy cho nhu cầu cụ thể nào nhất?",
    "Công việc chính quyết định hiệu năng của bộ máy là gì?",
)

DETAIL_PREFIXES = (
    "Cần máy chuyên cho",
    "Mình dùng máy hằng ngày để",
    "Cấu hình phải xử lý tốt",
    "Tư vấn máy phục vụ",
    "Công việc chính của mình là",
)

KEEP_MESSAGES = (
    "ưu tiên GPU hơn CPU",
    "mình chủ yếu chơi game AAA ở 2K 60 FPS",
    "công việc là dựng video Premiere hằng ngày",
    "mình chạy nhiều máy ảo và Docker",
    "ưu tiên máy ổn định để xử lý dữ liệu nặng",
    "mình chơi eSports ở tần số quét cao",
    "cần stream đồng thời khi chơi game",
    "mình dùng Blender để render cảnh lớn",
    "cần chạy mô hình AI và xử lý dữ liệu",
    "công việc văn phòng gồm bảng tính lớn và nhiều tab",
)


def _request(
    requirements: list[str],
    budget: int | None,
    *,
    components: dict[str, str] | None = None,
    brands: dict[str, str] | None = None,
    quantity: int = 1,
    clarification_count: int = 0,
    force_select: bool = False,
    response_mode: str | None = None,
    response_facts: dict | None = None,
    selection_facts: dict | None = None,
) -> dict:
    return {
        "requirements": requirements,
        "budget": budget,
        "components": components or {},
        "mandatory_brands": brands or {},
        "quantity": quantity,
        "clarification_count": clarification_count,
        "force_select": force_select,
        "response_mode": response_mode,
        "response_facts": response_facts or {},
        "selection_facts": selection_facts or {},
    }


def _retrieve(catalog: ShopCatalog, request: dict) -> list:
    candidates = catalog.search_builds(BuildQuery(
        text=" ".join(request["requirements"]),
        budget=request["budget"],
        required_components=request["components"],
        brands=request["mandatory_brands"],
        limit=5,
    ))
    if len(candidates) < 3:
        raise ValueError(f"Production retrieval returned only {len(candidates)} candidates")
    return candidates


def _reason(build) -> str:
    purpose = build.detailed_purpose.strip()
    workload = str(build.attributes.get("Primary_Workload", "")).strip()
    return f"{purpose} Công việc chính phù hợp là {workload}."


def _row(request: dict, candidates: list, decision: PcBuildDecision) -> dict:
    if request["response_mode"]:
        decision = _validate_response(
            decision,
            candidates,
            request["response_mode"],
            request["response_facts"],
        )
    else:
        decision = _validate_decision(
            decision,
            candidates,
            bool(request["force_select"]),
            request["selection_facts"],
        )
    request_json = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
    candidate_json = json.dumps(
        [_candidate_projection(candidate) for candidate in candidates],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    messages = PC_BUILD_RERANK_TEMPLATE.format_messages(
        request_json=request_json,
        candidate_json=candidate_json,
    )
    return {"messages": [
        {"role": "system", "content": messages[0].content},
        {"role": "user", "content": messages[1].content},
        {"role": "assistant", "content": decision.model_dump_json()},
    ]}


def _select_row(catalog: ShopCatalog, request: dict, candidates: list | None = None) -> dict:
    candidates = candidates or _retrieve(catalog, request)
    selected = candidates[0]
    selection_facts = {
        candidate.build_id: {
            "quantity": f"{request['quantity']} bộ" if request["quantity"] > 1 else None,
            "total_for_quantity": (
                format_approx_million(candidate.total_price * request["quantity"])
                if request["quantity"] > 1 else None
            ),
        }
        for candidate in candidates
    }
    request["selection_facts"] = selection_facts
    selected_facts = selection_facts[selected.build_id]
    response = "Dạ, em đề xuất cấu hình sau:\n" + format_build_context(selected)
    if selected_facts["total_for_quantity"]:
        response += (
            f"- Số lượng: {selected_facts['quantity']}\n"
            f"- Tổng cho số lượng này: {selected_facts['total_for_quantity']}\n"
        )
    return _row(request, candidates, PcBuildDecision(
        action="select",
        selected_build_id=selected.build_id,
        recommendation_reason=_reason(selected),
        response_text=response,
    ))


def _turn(
    catalog: ShopCatalog,
    current_build,
    latest_message: str,
    current_components: dict[str, str] | None = None,
) -> dict:
    mentions = catalog.match_build_entities(latest_message)
    context = PcBuildContext(
        build_id=current_build.build_id if current_build else None,
        requirements=["build pc theo nhu cầu"],
        required_components=current_components or {},
    )
    return {
        "latest_message": latest_message,
        "pending_question": None,
        "context": context.model_dump(exclude_none=True),
        "catalog_mentions": {
            "components": mentions.components,
            "brands": {
                brand: sorted(categories)
                for brand, categories in mentions.brands.items()
            },
        },
        "current_build": None if current_build is None else {
            "build_id": current_build.build_id,
            "components": {
                category: part.model
                for category, part in current_build.components.items()
            },
        },
    }


def _turn_row(turn: dict, plan: PcBuildTurnPlan) -> dict:
    plan = _validate_turn_plan(plan, turn)
    turn_json = json.dumps(turn, ensure_ascii=False, separators=(",", ":"))
    messages = PC_BUILD_TURN_TEMPLATE.format_messages(turn_json=turn_json)
    return {"messages": [
        {"role": "system", "content": messages[0].content},
        {"role": "user", "content": messages[1].content},
        {"role": "assistant", "content": plan.model_dump_json()},
    ]}


def _budget_row(candidate, budget: int, quantity: int) -> dict:
    facts = {
        "minimum_per_unit": format_approx_million(candidate.total_price),
        "minimum_total": (
            format_approx_million(candidate.total_price * quantity)
            if quantity > 1 else None
        ),
        "budget_per_unit": format_approx_million(budget),
        "quantity": f"{quantity} bộ" if quantity > 1 else None,
    }
    if quantity > 1:
        message = (
            f"Với {facts['quantity']}, cấu hình hợp lệ rẻ nhất có giá {facts['minimum_per_unit']} mỗi bộ, "
            f"tổng cộng {facts['minimum_total']}, trong khi ngân sách hiện tại là "
            f"{facts['budget_per_unit']} mỗi bộ. Bạn muốn tăng ngân sách mỗi bộ hay thay đổi yêu cầu?"
        )
    else:
        message = (
            f"Giá mỗi bộ thấp nhất đáp ứng đầy đủ yêu cầu là {facts['minimum_per_unit']}, "
            f"cao hơn ngân sách {facts['budget_per_unit']}. Bạn muốn tăng ngân sách hay điều chỉnh yêu cầu?"
        )
    request = _request(
        ["build pc"],
        budget,
        quantity=quantity,
        response_mode="budget_gap",
        response_facts=facts,
    )
    return _row(request, [candidate], PcBuildDecision(
        action="respond",
        response_text=message,
    ))


def _unavailable_constraints(catalog: ShopCatalog, builds: list) -> list[dict[str, str]]:
    combinations = []
    for cpu_build in builds:
        for gpu_build in reversed(builds):
            components = {
                "cpu": cpu_build.components["cpu"].model,
                "gpu": gpu_build.components["gpu"].model,
            }
            if components in combinations:
                continue
            candidates = catalog.search_builds(BuildQuery(
                text="",
                required_components=components,
                limit=1,
            ))
            if not candidates:
                combinations.append(components)
                if len(combinations) == 5:
                    return combinations
    raise RuntimeError("Catalog does not contain five unavailable component combinations")


def _different_build(builds: list, current, category: str, offset: int):
    for candidate in builds[offset:] + builds[:offset]:
        if candidate.components[category].model != current.components[category].model:
            return candidate
    raise RuntimeError(f"Catalog has no alternative {category} model")


def _workload_records(builds: list) -> list:
    unique = {}
    for build in builds:
        workload = str(build.attributes.get("Primary_Workload", "")).strip()
        purpose_code = str(build.attributes.get("Purpose_Code", "")).strip()
        if workload and purpose_code:
            unique.setdefault((purpose_code, workload), build)
    return [unique[key] for key in sorted(unique)]


def _common_components(builds: list) -> list[tuple[str, str]]:
    counts = Counter(
        (category, part.model)
        for build in builds
        for category, part in build.components.items()
    )
    return [key for key, count in counts.most_common() if count >= 5]


def _common_brands(builds: list) -> list[tuple[str, str]]:
    counts = Counter(
        (category, part.brand)
        for build in builds
        for category, part in build.components.items()
        if part.brand
    )
    return [key for key, count in counts.most_common() if count >= 5]


def generate() -> list[dict]:
    rng = random.Random(SEED)
    catalog = ShopCatalog.load(CATALOG_DIR)
    builds = list(catalog._builds.values())
    workloads = _workload_records(builds)
    if len(workloads) < 20:
        raise RuntimeError("V3 catalog does not contain enough distinct workload labels")

    rows = []

    # 40 detailed single-turn selects.
    for index in range(40):
        source = workloads[index % len(workloads)]
        workload = str(source.attributes["Primary_Workload"]).strip()
        request = _request(
            [f"{DETAIL_PREFIXES[index % len(DETAIL_PREFIXES)]} {workload}"],
            max(source.total_price + 5_000_000, 15_000_000),
        )
        rows.append(_select_row(catalog, request))

    # 20 accumulated clarification-answer selects.
    for index in range(20):
        source = workloads[(index + 9) % len(workloads)]
        workload = str(source.attributes["Primary_Workload"]).strip()
        request = _request(
            ["mình cần build một bộ PC", f"Nhu cầu cụ thể là {workload}"],
            max(source.total_price + 5_000_000, 15_000_000),
            clarification_count=1,
        )
        rows.append(_select_row(catalog, request))

    # Four exact-component, three mandatory-brand, two quantity, and one
    # no-budget enterprise select.
    for index, (category, model) in enumerate(_common_components(builds)[:4]):
        source = workloads[index]
        workload = str(source.attributes["Primary_Workload"]).strip()
        request = _request(
            [f"Cần máy cho {workload}, bắt buộc dùng {model}"],
            300_000_000,
            components={category: model},
        )
        rows.append(_select_row(catalog, request))

    for index, (category, brand) in enumerate(_common_brands(builds)[:3]):
        source = workloads[index + 4]
        workload = str(source.attributes["Primary_Workload"]).strip()
        request = _request(
            [f"Cần máy cho {workload}, {category} phải là {brand}"],
            300_000_000,
            brands={category: brand},
        )
        rows.append(_select_row(catalog, request))

    for index, quantity in enumerate((3, 10)):
        request = _request(
            [f"Mua {quantity} bộ máy cho văn phòng xử lý bảng tính và nhiều tab trình duyệt"],
            30_000_000,
            quantity=quantity,
        )
        rows.append(_select_row(catalog, request))

    rows.append(_select_row(catalog, _request([
        "Doanh nghiệp cần workstation chạy mô phỏng, máy ảo và xử lý dữ liệu nặng; chi phí không phải ưu tiên"
    ], None)))

    # Ten forced selections after the two-question limit.
    for index in range(10):
        request = _request(
            ["mình cần build pc", "chưa có ưu tiên cụ thể", f"hãy chọn phương án phù hợp số {index + 1}"],
            None,
            clarification_count=2,
            force_select=True,
        )
        rows.append(_select_row(catalog, request))

    # Ten budget-only, ten generally vague, and ten gaming-only clarifications.
    for index, millions in enumerate((8, 10, 12, 14, 16, 18, 22, 24, 26, 28)):
        budget = millions * 1_000_000
        request = _request([f"build pc ngân sách {budget // 1_000_000} triệu"], budget)
        rows.append(_row(request, _retrieve(catalog, request), PcBuildDecision(
            action="clarify",
            clarification_question=CLARIFICATION_QUESTIONS[index],
        )))

    for index, requirement in enumerate(VAGUE_REQUIREMENTS):
        request = _request([requirement], None)
        rows.append(_row(request, _retrieve(catalog, request), PcBuildDecision(
            action="clarify",
            clarification_question=CLARIFICATION_QUESTIONS[index],
        )))

    for requirement, question in zip(
        VAGUE_GAMING_REQUIREMENTS,
        GAMING_CLARIFICATION_QUESTIONS,
    ):
        request = _request([requirement], None)
        rows.append(_row(request, _retrieve(catalog, request), PcBuildDecision(
            action="clarify",
            clarification_question=question,
        )))

    # Ten catalog-derived budget-gap responses use the same production decision
    # payload and the exact cheapest candidate.
    cheapest = catalog.search_builds(BuildQuery(
        text="build pc",
        price_order="asc",
        limit=1,
    ))[0]
    for index, quantity in enumerate((1, 2, 3, 5, 10, 1, 2, 3, 5, 10)):
        rows.append(_budget_row(
            cheapest,
            max(1_000_000, cheapest.total_price - (index + 1) * 500_000),
            quantity,
        ))

    # Five impossible canonical component combinations and five missing IDs
    # teach factual responses without formatter-authored prose.
    for components in _unavailable_constraints(catalog, builds):
        facts = {"components": components, "mandatory_brands": {}}
        request = _request(
            ["build pc với linh kiện bắt buộc"],
            None,
            components=components,
            response_mode="unavailable",
            response_facts=facts,
        )
        models = " và ".join(components.values())
        rows.append(_row(request, [], PcBuildDecision(
            action="respond",
            response_text=(
                f"Hiện không có cấu hình nào đáp ứng đồng thời {models}. "
                "Bạn muốn bỏ bớt ràng buộc nào hoặc bắt đầu lại?"
            ),
        )))

    for index in range(5):
        build_id = None if index == 0 else f"BUILD-KHONG-CO-{index}"
        facts = {"build_id": build_id}
        request = _request(
            ["hỏi về bộ PC đã chọn"],
            None,
            response_mode="missing_build",
            response_facts=facts,
        )
        subject = (
            f"bộ PC mã {build_id}"
            if build_id else "dữ liệu bộ PC hiện tại"
        )
        rows.append(_row(request, [], PcBuildDecision(
            action="respond",
            response_text=(
                f"Em không tìm thấy {subject} trong catalog. "
                "Bạn muốn cung cấp lại yêu cầu hay kiểm tra một mã khác?"
            ),
        )))

    # Twenty normal requirement/clarification answers that keep hard state.
    for index in range(20):
        current = builds[index]
        message = KEEP_MESSAGES[index % len(KEEP_MESSAGES)]
        if index >= len(KEEP_MESSAGES):
            message += " trong phiên làm việc chính"
        rows.append(_turn_row(
            _turn(catalog, current, message),
            PcBuildTurnPlan(),
        ))

    # Twenty exact component replacements recognized by the catalog.
    for index in range(20):
        category = ("cpu", "gpu", "mainboard")[index % 3]
        current = builds[index + 20]
        target = _different_build(builds, current, category, index + 1)
        message = f"đổi {category} sang {target.components[category].model}"
        rows.append(_turn_row(
            _turn(
                catalog,
                current,
                message,
                {category: current.components[category].model},
            ),
            PcBuildTurnPlan(set_components=[category]),
        ))

    # Fifteen locks copy facts from the canonical current build.
    for index in range(15):
        category = ("cpu", "gpu", "mainboard")[index % 3]
        current = builds[index + 40]
        message = f"giữ nguyên {category} của bộ hiện tại"
        rows.append(_turn_row(
            _turn(catalog, current, message),
            PcBuildTurnPlan(lock_components=[category]),
        ))

    # Ten explicit removals release an existing hard constraint.
    for index in range(10):
        category = ("cpu", "gpu", "mainboard")[index % 3]
        current = builds[index + 55]
        message = f"không cần cố định {category} nữa"
        rows.append(_turn_row(
            _turn(
                catalog,
                current,
                message,
                {category: current.components[category].model},
            ),
            PcBuildTurnPlan(remove_components=[category]),
        ))

    # Fifteen mixed turns exercise lock+replace and remove+replace together.
    for index in range(15):
        set_category = ("gpu", "mainboard", "cpu")[index % 3]
        other_categories = [
            category for category in ("cpu", "gpu", "mainboard")
            if category != set_category
        ]
        state_category = other_categories[index % 2]
        current = builds[index + 65]
        target = _different_build(builds, current, set_category, index + 10)
        if index % 2 == 0:
            message = (
                f"giữ nguyên {state_category} nhưng đổi {set_category} sang "
                f"{target.components[set_category].model}"
            )
            update = PcBuildTurnPlan(
                set_components=[set_category],
                lock_components=[state_category],
            )
            stored = {}
        else:
            message = (
                f"bỏ cố định {state_category} và đổi {set_category} sang "
                f"{target.components[set_category].model}"
            )
            update = PcBuildTurnPlan(
                set_components=[set_category],
                remove_components=[state_category],
            )
            stored = {state_category: current.components[state_category].model}
        rows.append(_turn_row(
            _turn(catalog, current, message, stored),
            update,
        ))

    # Twenty planner examples replace runtime case tables for money, quantity,
    # session control, Q&A routing, mandatory brands, and exact price order.
    current = builds[0]
    budget_cases = (
        ("đặt ngân sách 30 triệu", PcBuildTurnPlan(budget_action="set", budget_value=30_000_000)),
        ("tăng thêm 5 triệu", PcBuildTurnPlan(budget_action="delta", budget_value=5_000_000)),
        ("giảm 3 triệu", PcBuildTurnPlan(budget_action="delta", budget_value=-3_000_000)),
        ("không giới hạn ngân sách", PcBuildTurnPlan(budget_action="clear")),
        ("ngân sách âm 10 triệu", PcBuildTurnPlan(budget_action="invalid")),
    )
    for message, plan in budget_cases:
        turn = _turn(catalog, current, message)
        turn["context"]["budget"] = 30_000_000
        rows.append(_turn_row(turn, plan))

    for quantity in (2, 5, 20):
        rows.append(_turn_row(
            _turn(catalog, current, f"mình cần {quantity} bộ"),
            PcBuildTurnPlan(quantity=quantity),
        ))

    for message, action in (
        ("làm lại từ đầu", "reset"),
        ("quên toàn bộ yêu cầu cũ", "reset"),
        ("cho mình bộ khác", "alternative"),
        ("đề xuất cấu hình khác nhưng giữ nhu cầu", "alternative"),
    ):
        rows.append(_turn_row(
            _turn(catalog, current, message),
            PcBuildTurnPlan(session_action=action),
        ))

    for message in ("bộ hiện tại dùng CPU gì", "giá bộ này bao nhiêu", "bộ này phù hợp việc gì"):
        rows.append(_turn_row(
            _turn(catalog, current, message),
            PcBuildTurnPlan(route="current_build_qa"),
        ))

    for category, brand in _common_brands(builds)[:3]:
        message = f"{category} bắt buộc phải là {brand}"
        rows.append(_turn_row(
            _turn(catalog, current, message),
            PcBuildTurnPlan(mandatory_brands={category: brand}),
        ))

    rows.append(_turn_row(
        _turn(catalog, current, "chọn bộ rẻ nhất"),
        PcBuildTurnPlan(price_order="asc"),
    ))
    rows.append(_turn_row(
        _turn(catalog, current, "chọn bộ đắt nhất"),
        PcBuildTurnPlan(price_order="desc"),
    ))

    for message in (
        "thời tiết hôm nay thế nào",
        "cảm ơn bạn",
        "cho mình hỏi giờ hiện tại",
        "xin chào",
        "mình muốn hỏi chuyện khác",
    ):
        rows.append(_turn_row(
            _turn(catalog, current, message),
            PcBuildTurnPlan(route="pass"),
        ))

    initial_messages = (
        "build pc chơi game AAA 2K 60 FPS",
        "cần máy render Blender cảnh lớn 4K",
        "workstation chạy nhiều máy ảo và Docker",
        "máy văn phòng xử lý bảng tính lớn",
        "máy AI huấn luyện mô hình hằng ngày",
        "build pc eSports tần số quét cao",
        "máy dựng Premiere footage 4K",
        "máy stream đồng thời khi chơi game",
        "workstation xử lý dữ liệu doanh nghiệp nặng",
        "build pc gaming hỗn hợp eSports và AAA",
    )
    for message in initial_messages:
        rows.append(_turn_row(_turn(catalog, None, message), PcBuildTurnPlan()))

    for millions in (10, 15, 20, 30, 50):
        rows.append(_turn_row(
            _turn(catalog, None, f"build pc ngân sách {millions} triệu"),
            PcBuildTurnPlan(budget_action="set", budget_value=millions * 1_000_000),
        ))

    for message in VAGUE_REQUIREMENTS[:5]:
        rows.append(_turn_row(_turn(catalog, None, message), PcBuildTurnPlan()))

    # Paired planner contrasts: mentioning a catalog model is not an update
    # unless the user explicitly asks to use or replace it.
    for index in range(20):
        category = ("cpu", "gpu", "mainboard")[index % 3]
        current = builds[index + 100]
        target = _different_build(builds, current, category, index + 20)
        model = target.components[category].model
        rows.append(_turn_row(
            _turn(catalog, current, f"hãy thay {category} hiện tại bằng {model}"),
            PcBuildTurnPlan(set_components=[category]),
        ))
        rows.append(_turn_row(
            _turn(catalog, current, f"mình chỉ đang cân nhắc {model}, chưa đổi {category}"),
            PcBuildTurnPlan(),
        ))

    # The same current component can be locked, released, or merely discussed.
    for index in range(10):
        category = ("cpu", "gpu", "mainboard")[index % 3]
        current = builds[index + 130]
        model = current.components[category].model
        rows.append(_turn_row(
            _turn(catalog, current, f"khóa {category} {model}, giữ nguyên linh kiện này"),
            PcBuildTurnPlan(lock_components=[category]),
        ))
        rows.append(_turn_row(
            _turn(catalog, current, f"bỏ ràng buộc {category} {model}", {category: model}),
            PcBuildTurnPlan(remove_components=[category]),
        ))
        rows.append(_turn_row(
            _turn(catalog, current, f"{category} {model} hiện tại ổn, nhưng chưa cần khóa"),
            PcBuildTurnPlan(),
        ))

    # Resolution and frame-rate numbers are not money; explicit currency is.
    non_budget_messages = (
        "chơi game 2K 60 FPS",
        "chơi game 4K 120 FPS",
        "dựng video 4K hàng ngày",
        "xuất hình 8K cho màn hình lớn",
        "eSports 1080p 240 FPS",
        "render 3D cảnh 4K",
        "stream 1440p 60 FPS",
        "chạy 2 máy ảo và Docker",
        "làm việc trên 4 màn hình",
        "huấn luyện mô hình 7B",
    )
    for index, millions in enumerate((12, 15, 20, 25, 30, 35, 40, 45, 50, 60)):
        rows.append(_turn_row(
            _turn(catalog, current, f"đặt ngân sách mỗi bộ là {millions} triệu"),
            PcBuildTurnPlan(budget_action="set", budget_value=millions * 1_000_000),
        ))
        rows.append(_turn_row(
            _turn(catalog, current, non_budget_messages[index]),
            PcBuildTurnPlan(),
        ))

    for message in (
        "ưu tiên GPU hơn CPU nhưng chưa đổi linh kiện",
        "ưu tiên CPU cho biên dịch, giữ ràng buộc hiện tại",
        "muốn máy ổn định hơn, chưa chỉ định model",
        "thích NVIDIA nhưng không bắt buộc hãng",
        "thích AMD nhưng vẫn chấp nhận phương án khác",
        "cần nhiều hiệu năng GPU hơn cho workload đã nói",
        "cần nhiều nhân CPU hơn cho workload đã nói",
        "ưu tiên ít ồn và tiết kiệm điện",
        "muốn cân bằng CPU và GPU",
        "giữ nhu cầu cũ, chỉ bổ sung ưu tiên độ bền",
    ):
        rows.append(_turn_row(_turn(catalog, current, message), PcBuildTurnPlan()))

    # Paired decision contrasts use identical valid candidates. Vague and
    # budget-only requests clarify; the same requests must select when forced.
    for index, requirement in enumerate(VAGUE_REQUIREMENTS):
        requirement = f"{requirement}, chưa xác định công việc chính"
        clarify_request = _request([requirement], None)
        candidates = _retrieve(catalog, clarify_request)
        rows.append(_row(clarify_request, candidates, PcBuildDecision(
            action="clarify",
            clarification_question=CLARIFICATION_QUESTIONS[index],
        )))
        rows.append(_select_row(catalog, _request(
            [requirement],
            None,
            clarification_count=2,
            force_select=True,
        ), candidates))

    for index, millions in enumerate((9, 11, 13, 15, 17, 19, 21, 23, 25, 27)):
        requirement = f"mình chỉ có ngân sách {millions} triệu, chưa nói nhu cầu"
        clarify_request = _request([requirement], millions * 1_000_000)
        candidates = _retrieve(catalog, clarify_request)
        rows.append(_row(clarify_request, candidates, PcBuildDecision(
            action="clarify",
            clarification_question=CLARIFICATION_QUESTIONS[index],
        )))
        rows.append(_select_row(catalog, _request(
            [requirement],
            millions * 1_000_000,
            clarification_count=2,
            force_select=True,
        ), candidates))

    # Response modes share the same production decision prompt.
    for index in range(5):
        facts = {"valid_budget": "lớn hơn 0"}
        request = _request(
            [f"ngân sách không hợp lệ trường hợp {index + 1}"],
            None,
            response_mode="invalid_budget",
            response_facts=facts,
        )
        rows.append(_row(request, [], PcBuildDecision(
            action="respond",
            response_text="Ngân sách cần lớn hơn 0. Bạn muốn cung cấp lại mức hợp lệ nào?",
        )))

    for build in builds[:5]:
        request = _request(
            ["hỏi về bộ PC hiện tại"],
            None,
            response_mode="build_qa",
            response_facts={"question": "Bộ này phù hợp việc gì?"},
        )
        rows.append(_row(request, [build], PcBuildDecision(
            action="respond",
            response_text=f"Bộ này phù hợp cho {build.detailed_purpose.strip()}.",
        )))

    rng.shuffle(rows)
    assert len(rows) == len({json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows}) == 405
    return rows


def main() -> None:
    rows = generate()
    OUTPUT.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(rows)} rows into {OUTPUT}")


if __name__ == "__main__":
    main()
