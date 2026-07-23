"""Generate PC Builder command-extraction SFT data from the production prompt."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pc_builder.extractor import build_extraction_messages
from app.pc_builder.models import (
    PcBuildAction,
    PcBuildCommand,
    PcBuildContext,
    PcBuildStatus,
    PendingQuestion,
)
from app.routing.models import RouteDecision, TaskRelation


OUTPUT = Path(__file__).with_name("pc_builder_adaptive.jsonl")
SEED = 3407
LEGACY_ROW_COUNT = 417

PURPOSES = (
    "chơi Valorant 1080p 240 FPS",
    "chơi game AAA 2K 60 FPS ở thiết lập cao",
    "chơi lẫn eSports và game AAA",
    "stream trong lúc chơi game 2K",
    "dựng video Premiere 4K hằng ngày",
    "render Blender cảnh 3D lớn",
    "huấn luyện mô hình AI cục bộ",
    "chạy nhiều máy ảo và Docker",
    "xử lý dữ liệu doanh nghiệp nặng",
    "lập trình và biên dịch dự án lớn",
    "làm AutoCAD và Revit chuyên nghiệp",
    "chỉnh ảnh Photoshop số lượng lớn",
    "văn phòng nhẹ với Word và trình duyệt",
    "Excel lớn và Power BI",
    "phát triển game bằng Unreal Engine",
    "sản xuất nhạc với nhiều plugin",
    "thiết kế đồ họa Illustrator",
    "mô phỏng kỹ thuật và tính toán khoa học",
    "máy trạm cho đội phân tích dữ liệu",
    "máy doanh nghiệp chạy tác vụ liên tục",
    "soạn Word, email, phần mềm kế toán và dưới 15 tab trình duyệt",
    "nhập liệu, in hóa đơn và họp trực tuyến hằng ngày",
    "quản lý bán hàng, trình duyệt và bộ Office cơ bản",
    "làm lễ tân với web, email và phần mềm đặt lịch",
    "học trực tuyến, soạn tài liệu và xem video",
    "máy thu ngân chạy phần mềm POS và trình duyệt",
    "Excel hàng triệu dòng, Power Query và Power BI hằng ngày",
    "xử lý ETL, truy vấn SQL lớn và nhiều bảng dữ liệu",
    "chạy mô hình tài chính lớn và nhiều file Excel đồng thời",
    "phân tích dữ liệu Python, Jupyter và cơ sở dữ liệu cục bộ",
    "chạy nhiều máy ảo, Docker và biên dịch song song",
    "vận hành dashboard doanh nghiệp trên nhiều màn hình liên tục",
    "chơi Valorant và CS2 1080p 360 FPS để thi đấu",
    "chơi CS2 1080p 240 FPS và ưu tiên độ trễ thấp",
    "chơi Liên Minh 1440p 165 FPS và stream",
    "chơi nhiều game eSports ở 1080p tần số quét cao",
    "chơi game AAA 1080p mức cao 60 FPS",
    "chơi game AAA 1440p ultra 90 FPS",
    "chơi game AAA 4K mức cao có ray tracing",
    "chơi Cyberpunk, Alan Wake 2 và Black Myth Wukong ở 2K",
    "chơi xen kẽ Valorant 240 FPS và game AAA 2K 60 FPS",
    "stream eSports 1080p đồng thời ghi hình",
    "chơi game mô phỏng nặng CPU và game AAA 1440p",
    "chơi game VR độ phân giải cao và game AAA",
)

VAGUE_PURPOSES = (
    "chơi game",
    "làm văn phòng",
    "làm AI",
    "làm đồ họa",
    "dựng phim",
    "lập trình",
    "render",
    "stream",
    "học tập",
    "làm việc",
    "dùng lâu dài",
    "cần máy mạnh",
    "dùng cho văn phòng",
    "chơi eSports",
    "chơi game AAA",
    "xử lý dữ liệu",
)

COMPONENTS = {
    "cpu": (
        "Intel Core i5-13600K",
        "Intel Core i7-14700K",
        "Intel Core i9-14900K",
        "AMD Ryzen 5 7600X",
        "AMD Ryzen 7 7800X3D",
        "AMD Ryzen 9 7950X",
        "Intel Core i5-12400F",
        "AMD Ryzen 9 9950X",
    ),
    "gpu": (
        "NVIDIA GeForce RTX 4060",
        "NVIDIA GeForce RTX 4070 SUPER",
        "NVIDIA GeForce RTX 4080 SUPER",
        "NVIDIA GeForce RTX 4090",
        "AMD Radeon RX 7600",
        "AMD Radeon RX 7800 XT",
        "AMD Radeon RX 7900 XTX",
        "Intel Arc A770",
    ),
    "mainboard": (
        "MSI PRO B650M-A WIFI",
        "Gigabyte B760 DS3H AX DDR5",
        "ASUS TUF GAMING Z790-PLUS WIFI",
        "ASRock B650E Steel Legend WiFi",
        "MSI MAG B850 TOMAHAWK WIFI",
        "Gigabyte X670 AORUS ELITE AX",
        "ASUS PRIME H610M-K D4",
        "ASRock Z890 Pro RS WiFi",
    ),
}


def _command(**values: Any) -> PcBuildCommand:
    return PcBuildCommand(**values)


def _context(**values: Any) -> PcBuildContext:
    defaults = {
        "status": PcBuildStatus.SELECTED,
        "build_id": "BUILD-01234",
        "budget": 30_000_000,
        "purpose": "chơi game AAA 2K",
    }
    defaults.update(values)
    return PcBuildContext(**defaults)


def _route(
    message: str,
    relation: TaskRelation,
) -> RouteDecision:
    return RouteDecision(
        handler_name="build_pc",
        rewritten_query=message,
        task_relation=relation,
        active_task_id=None if relation == TaskRelation.NEW_REQUEST else "pc-build",
    )


def _row(
    message: str,
    command: PcBuildCommand,
    *,
    context: PcBuildContext | None = None,
    relation: TaskRelation = TaskRelation.NEW_REQUEST,
    history: list[dict[str, str]] | None = None,
) -> dict[str, list[dict[str, str]]]:
    messages = build_extraction_messages(
        user_message=message,
        recent_history=history or [],
        current_context=context or PcBuildContext(),
        route_decision=_route(message, relation),
    )
    messages.append({
        "role": "assistant",
        "content": command.model_dump_json(),
    })
    return {"messages": messages}


def _create_rows() -> list[dict]:
    rows: list[dict] = []

    for index, purpose in enumerate(VAGUE_PURPOSES):
        millions = 20 + index * 3
        detailed_purpose = PURPOSES[index]
        rows.append(_row(
            f"build PC {millions} triệu để {purpose}",
            _command(
                action=PcBuildAction.CREATE,
                budget=millions * 1_000_000,
                budget_scope="total",
                purpose=purpose,
                purpose_status="clarify",
            ),
        ))
        rows.append(_row(
            f"tư vấn một bộ PC để {purpose}",
            _command(
                action=PcBuildAction.CREATE,
                purpose=purpose,
                purpose_status="clarify",
            ),
        ))
        rows.append(_row(
            f"build PC {millions} triệu để {purpose}, đừng hỏi thêm và tự chọn phương án phù hợp nhất",
            _command(
                action=PcBuildAction.CREATE,
                budget=millions * 1_000_000,
                budget_scope="total",
                purpose=purpose,
                purpose_status="ready",
            ),
        ))
        rows.append(_row(
            f"tư vấn một bộ PC để {purpose}, chọn luôn giúp mình không cần hỏi lại",
            _command(
                action=PcBuildAction.CREATE,
                purpose=purpose,
                purpose_status="ready",
            ),
        ))
        rows.append(_row(
            f"build PC {millions} triệu để {detailed_purpose}",
            _command(
                action=PcBuildAction.CREATE,
                budget=millions * 1_000_000,
                budget_scope="total",
                purpose=detailed_purpose,
            ),
        ))
        rows.append(_row(
            f"tư vấn một bộ PC để {detailed_purpose}",
            _command(
                action=PcBuildAction.CREATE,
                purpose=detailed_purpose,
            ),
        ))

    for index, purpose in enumerate(PURPOSES):
        for millions in (18 + index, 38 + index):
            message = f"build PC ngân sách {millions} triệu để {purpose}"
            rows.append(_row(message, _command(
                action=PcBuildAction.CREATE,
                budget=millions * 1_000_000,
                budget_scope="total",
                purpose=purpose,
            )))

        message = f"mình cần một bộ PC để {purpose}"
        rows.append(_row(message, _command(
            action=PcBuildAction.CREATE,
            purpose=purpose,
        )))

    for millions in (10, 15, 20, 25, 30, 35, 40, 50, 70, 100):
        message = f"tư vấn PC trong khoảng {millions} triệu"
        rows.append(_row(message, _command(
            action=PcBuildAction.CREATE,
            budget=millions * 1_000_000,
            budget_scope="total",
        )))

    for category, models in COMPONENTS.items():
        for index, model in enumerate(models):
            millions = 25 + index * 5
            message = f"build PC {millions} triệu bắt buộc dùng {model}"
            rows.append(_row(message, _command(
                action=PcBuildAction.CREATE,
                budget=millions * 1_000_000,
                budget_scope="total",
                required_components={category: model},
            )))

    workloads = PURPOSES[:10]
    for index, quantity in enumerate(range(2, 12)):
        millions = quantity * (18 + index)
        purpose = workloads[index]
        message = f"cần {quantity} bộ PC để {purpose}, tổng ngân sách {millions} triệu"
        rows.append(_row(message, _command(
            action=PcBuildAction.CREATE,
            budget=millions * 1_000_000,
            budget_scope="total",
            purpose=purpose,
            quantity=quantity,
        )))

        unit = 20 + index
        message = f"mua {quantity} máy cho {purpose}, mỗi máy {unit} triệu"
        rows.append(_row(message, _command(
            action=PcBuildAction.CREATE,
            budget=unit * 1_000_000,
            budget_scope="per_unit",
            purpose=purpose,
            quantity=quantity,
        )))

    return rows


def _update_rows() -> list[dict]:
    rows: list[dict] = []
    current = _context()

    for category, models in COMPONENTS.items():
        for model in models:
            message = f"đổi {category} của bộ hiện tại sang {model}"
            rows.append(_row(
                message,
                _command(
                    action=PcBuildAction.UPDATE,
                    required_components={category: model},
                ),
                context=current,
                relation=TaskRelation.MODIFY_TASK,
            ))

    preferences = ("mạnh hơn", "mát hơn", "ổn định hơn", "phù hợp công việc hơn")
    for index, category in enumerate(("cpu", "gpu", "mainboard") * 4):
        other = ("gpu", "mainboard", "cpu")[index % 3]
        preference = preferences[index // 3]
        message = f"giữ nguyên {category}, còn {other} thì ưu tiên loại {preference}"
        rows.append(_row(
            message,
            _command(
                action=PcBuildAction.UPDATE,
                preferred_components={other: [preference]},
                keep_components=[category],
            ),
            context=current,
            relation=TaskRelation.MODIFY_TASK,
        ))

    for index, purpose in enumerate(PURPOSES):
        message = f"đổi nhu cầu của bộ này sang {purpose}"
        rows.append(_row(
            message,
            _command(action=PcBuildAction.UPDATE, purpose=purpose),
            context=current,
            relation=TaskRelation.MODIFY_TASK,
            history=[
                {"role": "user", "content": "tư vấn cho mình một bộ PC"},
                {"role": "assistant", "content": "Bạn sẽ dùng máy chủ yếu cho công việc nào?"},
            ],
        ))

    for millions in (12, 18, 24, 30, 36, 42, 50, 60, 80, 120):
        message = f"đặt lại ngân sách của bộ hiện tại thành {millions} triệu"
        rows.append(_row(
            message,
            _command(
                action=PcBuildAction.UPDATE,
                budget=millions * 1_000_000,
                budget_scope="total",
            ),
            context=current,
            relation=TaskRelation.MODIFY_TASK,
        ))

    for brand in ("NVIDIA", "AMD", "Intel", "ASUS", "MSI", "Gigabyte", "ASRock", "Zotac"):
        message = f"bộ tiếp theo không dùng linh kiện hãng {brand}"
        rows.append(_row(
            message,
            _command(action=PcBuildAction.UPDATE, excluded_brands=[brand]),
            context=current,
            relation=TaskRelation.MODIFY_TASK,
        ))

    return rows


def _context_rows() -> list[dict]:
    rows: list[dict] = []

    for millions in (8, 12, 16, 20, 25, 30, 40, 50, 75, 100):
        message = f"{millions} triệu"
        rows.append(_row(
            message,
            _command(
                action=PcBuildAction.UPDATE,
                budget=millions * 1_000_000,
                budget_scope="total",
            ),
            context=_context(
                status=PcBuildStatus.COLLECTING,
                build_id=None,
                budget=None,
                purpose="chơi game AAA",
                pending_question=PendingQuestion.BUDGET,
            ),
            relation=TaskRelation.CONTINUE_TASK,
            history=[
                {"role": "user", "content": "mình muốn build PC chơi game AAA"},
                {"role": "assistant", "content": "Bạn dự trù ngân sách khoảng bao nhiêu?"},
            ],
        ))

    budget_answers = (("500k", 500_000), ("750k", 750_000), ("2 củ", 2_000_000))
    for message, budget in budget_answers:
        rows.append(_row(
            message,
            _command(
                action=PcBuildAction.UPDATE,
                budget=budget,
                budget_scope="total",
            ),
            context=_context(
                status=PcBuildStatus.COLLECTING,
                build_id=None,
                budget=None,
                purpose="máy văn phòng",
                pending_question=PendingQuestion.BUDGET,
            ),
            relation=TaskRelation.CONTINUE_TASK,
        ))

    for purpose in PURPOSES[:10]:
        rows.append(_row(
            purpose,
            _command(action=PcBuildAction.UPDATE, purpose=purpose),
            context=_context(
                status=PcBuildStatus.COLLECTING,
                build_id=None,
                budget=30_000_000,
                purpose=None,
                pending_question=PendingQuestion.PURPOSE,
            ),
            relation=TaskRelation.CONTINUE_TASK,
            history=[
                {"role": "user", "content": "mình có 30 triệu để build PC"},
                {"role": "assistant", "content": "Bạn dùng máy chủ yếu cho nhu cầu nào?"},
            ],
        ))

    for index, quantity in enumerate(range(2, 7)):
        total = 50 + index * 20
        message = f"{total} triệu là tổng cho cả {quantity} bộ"
        rows.append(_row(
            message,
            _command(
                action=PcBuildAction.UPDATE,
                budget=total * 1_000_000,
                budget_scope="total",
            ),
            context=_context(
                status=PcBuildStatus.COLLECTING,
                build_id=None,
                budget=None,
                quantity=quantity,
                pending_question=PendingQuestion.BUDGET_SCOPE,
            ),
            relation=TaskRelation.CONTINUE_TASK,
        ))

        unit = 20 + index * 5
        message = f"ngân sách {unit} triệu là cho mỗi máy"
        rows.append(_row(
            message,
            _command(
                action=PcBuildAction.UPDATE,
                budget=unit * 1_000_000,
                budget_scope="per_unit",
            ),
            context=_context(
                status=PcBuildStatus.COLLECTING,
                build_id=None,
                budget=None,
                quantity=quantity,
                pending_question=PendingQuestion.BUDGET_SCOPE,
            ),
            relation=TaskRelation.CONTINUE_TASK,
        ))

    return rows


def _control_and_edge_rows() -> list[dict]:
    rows: list[dict] = []
    current = _context()

    for message in (
        "cho mình một cấu hình khác",
        "đề xuất bộ khác nhưng giữ nguyên nhu cầu",
        "mình muốn xem phương án thay thế",
        "còn lựa chọn nào khác không",
        "đổi sang bộ khác cùng ngân sách",
        "tìm một cấu hình khác cho mình",
        "không chọn bộ này, xem bộ kế tiếp",
        "giữ yêu cầu cũ và chọn máy khác",
    ):
        rows.append(_row(
            message,
            _command(action=PcBuildAction.ALTERNATIVE),
            context=current,
            relation=TaskRelation.MODIFY_TASK,
        ))

    for message in (
        "làm lại yêu cầu build PC từ đầu",
        "xóa cấu hình hiện tại và bắt đầu lại",
        "bỏ hết yêu cầu cũ",
        "reset bộ PC đang tư vấn",
        "quên cấu hình này đi, mình làm lại",
        "hủy trạng thái build PC hiện tại",
    ):
        rows.append(_row(
            message,
            _command(action=PcBuildAction.RESET),
            context=current,
            relation=TaskRelation.MODIFY_TASK,
        ))

    for message in (
        "bộ hiện tại dùng CPU gì",
        "GPU của cấu hình này là model nào",
        "mainboard trong bộ này có WiFi không",
        "tổng giá cấu hình hiện tại bao nhiêu",
        "bộ này chơi Cyberpunk 2K ổn không",
        "cấu hình đang chọn phù hợp công việc gì",
        "bộ hiện tại có điểm gì cần lưu ý",
        "CPU và GPU của máy này có cân bằng không",
        "mã BuildID của bộ đang chọn là gì",
        "cấu hình này dùng card hãng nào",
    ):
        rows.append(_row(
            message,
            _command(action=PcBuildAction.QUESTION_CURRENT_BUILD),
            context=current,
            relation=TaskRelation.TASK_QUESTION,
        ))

    for message, purpose in (
        ("build PC chơi game 2K 60 FPS", "chơi game 2K 60 FPS"),
        ("cần máy chơi game 4K 120 FPS", "chơi game 4K 120 FPS"),
        ("máy dựng video 4K mỗi ngày", "dựng video 4K mỗi ngày"),
        ("PC eSports 1080p 240 FPS", "eSports 1080p 240 FPS"),
        ("máy render cảnh 8K", "render cảnh 8K"),
        ("PC stream 1440p 60 FPS", "stream 1440p 60 FPS"),
        ("máy AI chạy mô hình 7B", "AI chạy mô hình 7B"),
        ("workstation dùng bốn màn hình", "dùng bốn màn hình"),
    ):
        rows.append(_row(message, _command(
            action=PcBuildAction.CREATE,
            purpose=purpose,
        )))

    for millions in (5, 10, 20, 30, 50):
        message = f"build PC âm {millions} triệu"
        rows.append(_row(message, _command(
            action=PcBuildAction.CREATE,
            budget=-millions * 1_000_000,
            budget_scope="total",
        )))

    return rows


def generate() -> list[dict]:
    rows = _create_rows() + _update_rows() + _context_rows() + _control_and_edge_rows()
    unique = {json.dumps(row, ensure_ascii=False, sort_keys=True): row for row in rows}
    if len(unique) != len(rows):
        raise ValueError("Duplicate training rows generated")

    rows = list(unique.values())
    random.Random(SEED).shuffle(rows)
    for row in rows:
        messages = row["messages"]
        if [message["role"] for message in messages] != ["system", "user", "assistant"]:
            raise ValueError("Training rows must use the production system/user payload")
        PcBuildCommand.model_validate_json(messages[-1]["content"])
        if "PcBuildTurnPlan" in messages[0]["content"] or "PcBuildDecision" in messages[0]["content"]:
            raise ValueError("Obsolete PC Builder schema leaked into training data")
    return rows


def main() -> None:
    if not OUTPUT.exists():
        raise FileNotFoundError(
            f"{OUTPUT} is required because it contains the preserved legacy training rows"
        )

    existing = [
        json.loads(line)
        for line in OUTPUT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    legacy_rows = [
        row
        for row in existing
        if "PcBuildCommand" not in row["messages"][0]["content"]
    ]
    if len(legacy_rows) != LEGACY_ROW_COUNT:
        raise ValueError(
            f"Expected {LEGACY_ROW_COUNT} preserved legacy rows, got {len(legacy_rows)}"
        )

    extractor_rows = generate()
    rows = legacy_rows + extractor_rows
    OUTPUT.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(
        f"Preserved {len(legacy_rows)} legacy rows and generated "
        f"{len(extractor_rows)} extractor rows into {OUTPUT}"
    )


if __name__ == "__main__":
    main()
