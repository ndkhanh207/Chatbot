import re

from app.compatibility.compatibility import resolve_component
from app.compatibility.compat_logic import (
    _get_field,
    check_cpu_gpu_compat,
    check_cpu_main_compat,
    check_gpu_main_compat,
)
from app.core.intent.history_context import build_intent_metadata
from app.memory.context_manager import ConversationContext
from app.pc_builder.formatter import format_approx_million


def _build_models(user_message: str, build_df) -> tuple[str, str, str] | None:
    match = re.search(r'\bBUILD[-_]\d+\b', user_message, re.IGNORECASE)
    if not match or build_df is None or build_df.empty:
        return None
    rows = build_df[build_df['BuildID'].astype(str).str.casefold() == match.group(0).casefold()]
    if rows.empty:
        return None
    row = rows.iloc[0]
    return row['CPU_Model'], row['Motherboard_Model'], row['GPU_Model']


def _describe_cpu(name: str, tier: int | None) -> str:
    if 'x3d' in name.lower():
        return "CPU rất mạnh cho gaming nhờ 3D V-Cache, cũng đủ tốt cho đa nhiệm/render vừa."
    if tier and tier >= 4:
        return "CPU rất mạnh, phù hợp tác vụ nặng và đa nhiệm."
    if tier and tier >= 3:
        return "CPU mạnh, phù hợp game và làm việc nặng vừa."
    return "CPU ở mức phổ thông/trung cấp."


def _describe_gpu(tier: int | None) -> str:
    if tier and tier >= 5:
        return "GPU cực mạnh, hợp 4K, render/AI và đồ họa rất nặng."
    if tier and tier >= 4:
        return "GPU rất mạnh, hợp game 2K/4K, render GPU, stream và đồ họa nặng."
    if tier and tier >= 3:
        return "GPU mạnh tầm cận cao cấp, hợp game 2K và đồ họa bán chuyên."
    return "GPU ở mức phổ thông/trung cấp."


def _infer_purpose(cpu_tier: int | None, gpu_tier: int | None) -> str:
    if (cpu_tier or 0) >= 3 and (gpu_tier or 0) >= 4:
        return "gaming cao cấp 2K/4K, stream, render GPU và đồ họa nặng."
    if (gpu_tier or 0) >= 4:
        return "game nặng, render GPU, stream hoặc AI nhẹ."
    if (gpu_tier or 0) >= 3:
        return "gaming 2K, render GPU, chỉnh sửa video, đồ họa và AI mức khá."
    if (cpu_tier or 0) >= 3:
        return "đa nhiệm, lập trình, render CPU và game mức tốt."
    return "nhu cầu phổ thông đến trung cấp."


def _format_review(cpu: dict, main: dict, gpu: dict) -> str:
    cpu_name = _get_field(cpu, 'tên', 'name', default='N/A')
    main_name = _get_field(main, 'tên', 'name', default='N/A')
    gpu_name = _get_field(gpu, 'tên', 'name', default='N/A')
    cpu_price = _get_field(cpu, 'giá', 'price', default=0) or 0
    main_price = _get_field(main, 'giá', 'price', default=0) or 0
    gpu_price = _get_field(gpu, 'giá', 'price', default=0) or 0

    cpu_main_check = check_cpu_main_compat(cpu, main)
    gpu_main_check = check_gpu_main_compat(gpu, main)
    cpu_gpu_check = check_cpu_gpu_compat(cpu, gpu)
    cpu_tier = cpu_gpu_check.get('cpu_tier')
    gpu_tier = cpu_gpu_check.get('gpu_tier')

    if cpu_main_check['is_compatible'] and gpu_main_check['is_compatible']:
        compatibility = "CPU và mainboard khớp socket; GPU dùng khe PCIe tương thích với mainboard."
        if gpu_main_check.get('warning'):
            compatibility += f" {gpu_main_check['warning']}"
    else:
        compatibility = " ".join(cpu_main_check.get('reasons', []))

    balance = cpu_gpu_check.get('warning') or "CPU và GPU cân bằng tốt, không thấy lệch hiệu năng rõ rệt."
    buy_advice = "cần cân nhắc cảnh báo cân bằng trên" if cpu_gpu_check.get('warning') else "combo đang cân bằng tốt"
    total = format_approx_million(cpu_price + main_price + gpu_price)

    return (
        "Dạ, em đánh giá combo 3 linh kiện này như sau:\n\n"
        f"- CPU: {cpu_name} - {format_approx_million(cpu_price)}\n"
        f"- GPU: {gpu_name} - {format_approx_million(gpu_price)}\n"
        f"- Mainboard: {main_name} - {format_approx_million(main_price)}\n"
        f"- Chi phí: tổng khoảng {total}\n\n"
        f"- Tương thích: {compatibility}\n"
        f"- Phù hợp: {_infer_purpose(cpu_tier, gpu_tier)}\n"
        f"- Hiệu năng: {_describe_cpu(cpu_name, cpu_tier)} {_describe_gpu(gpu_tier)} {balance}\n"
        f"- Giá trị: tổng {total}; phù hợp khi các nhu cầu trên là ưu tiên chính.\n"
        f"- Có nên mua: nên nếu đúng nhu cầu; {buy_advice} và cần kiểm tra các linh kiện còn thiếu trước khi chốt."
    )


def handle_combo_review(
    parsed_intent,
    user_message: str,
    knowledge_base,
    vector_store,
    user_uid: str,
    session_id: str,
    build_df=None,
) -> dict:
    names = (parsed_intent.cpu, parsed_intent.mainboard, parsed_intent.gpu)
    if any(not name or name.lower() == 'none' for name in names):
        names = _build_models(user_message, build_df) or names

    cpu = resolve_component(names[0], 'CPU', knowledge_base, vector_store)
    main = resolve_component(names[1], 'MAINBOARD', knowledge_base, vector_store)
    gpu = resolve_component(names[2], 'GPU', knowledge_base, vector_store)
    print(f"🔍 [COMBO REVIEW] CPU={names[0]} | Mainboard={names[1]} | GPU={names[2]}")
    print(f"🔹 Components resolved: CPU={bool(cpu)}, Mainboard={bool(main)}, GPU={bool(gpu)}")
    if not all((cpu, main, gpu)):
        reply = "Dạ, em chưa tìm thấy đủ CPU, GPU và mainboard trong dữ liệu shop để đánh giá chính xác combo này ạ."
    else:
        reply = _format_review(cpu, main, gpu)

    print("[DEBUG COMBO REVIEW FINAL RESPONSE]")
    print(reply)
    print("=" * 60 + "\n")
    ConversationContext(user_uid, session_id).commit(
        user_message,
        reply,
        build_intent_metadata(parsed_intent),
    )
    return {'chatbot_reply': reply}
