import re

from app.compatibility.compatibility import resolve_component
from app.compatibility.compat_logic import (
    _get_field,
    check_cpu_main_compat,
    check_gpu_main_compat,
)
from app.core.intent.history_context import build_intent_metadata
from app.memory.context_manager import ConversationContext
from app.pc_builder.formatter import format_approx_million
from app.chat.models import DomainRequest, ChatResult
from app.chat.contracts import DomainHandler
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog
def _build_models(user_message: str, catalog: ShopCatalog) -> tuple[str, str, str] | None:
    match = re.search(r'\bBUILD[-_]\d+\b', user_message, re.IGNORECASE)
    if not match:
        return None
    build = catalog.get_build(match.group(0))
    if build is None:
        return None
    return build.components['cpu'].model, build.components['mainboard'].model, build.components['gpu'].model


def _format_review(cpu: dict, main: dict, gpu: dict) -> str:
    cpu_name = _get_field(cpu, 'tên', 'name', default='N/A')
    main_name = _get_field(main, 'tên', 'name', default='N/A')
    gpu_name = _get_field(gpu, 'tên', 'name', default='N/A')
    cpu_price = _get_field(cpu, 'giá', 'price', default=0) or 0
    main_price = _get_field(main, 'giá', 'price', default=0) or 0
    gpu_price = _get_field(gpu, 'giá', 'price', default=0) or 0

    cpu_main_check = check_cpu_main_compat(cpu, main)
    gpu_main_check = check_gpu_main_compat(gpu, main)

    if cpu_main_check['is_compatible'] is True and gpu_main_check['is_compatible'] is True:
        compatibility = "CPU và mainboard khớp socket; GPU dùng khe PCIe tương thích với mainboard."
        if gpu_main_check['bandwidth_limited']:
            compatibility += " Băng thông GPU chạy theo thế hệ PCIe của mainboard."
    else:
        reasons = []
        if cpu_main_check['is_compatible'] is False:
            reasons.append(
                f"CPU dùng socket {cpu_main_check['cpu_socket']}, mainboard dùng "
                f"{cpu_main_check['mainboard_socket']}, nên không lắp được với nhau."
            )
        elif cpu_main_check['is_compatible'] is None:
            reasons.append("Không đủ dữ liệu socket để xác nhận CPU và mainboard.")
        if gpu_main_check['is_compatible'] is None:
            reasons.append("Không đủ dữ liệu PCIe để xác nhận GPU và mainboard.")
        compatibility = " ".join(reasons)

    total = format_approx_million(cpu_price + main_price + gpu_price)

    return (
        "Dạ, em đánh giá combo 3 linh kiện này như sau:\n\n"
        f"- CPU: {cpu_name} - {format_approx_million(cpu_price)}\n"
        f"- GPU: {gpu_name} - {format_approx_million(gpu_price)}\n"
        f"- Mainboard: {main_name} - {format_approx_million(main_price)}\n"
        f"- Chi phí: tổng khoảng {total}\n\n"
        f"- Tương thích: {compatibility}\n"
        "- Hiệu năng/phù hợp: catalog chưa có benchmark theo workload để kết luận chính xác.\n"
        f"- Giá trị: tổng ba linh kiện khoảng {total}.\n"
        "- Có nên mua: cần đối chiếu nhu cầu và kiểm tra RAM, nguồn, tản nhiệt, case trước khi chốt."
    )


class ComboReviewHandler(DomainHandler):
    def __init__(self, *, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(
        self,
        request: DomainRequest,
        intent: ParsedIntent,
    ) -> ChatResult:
        user_message = request.user_message
        catalog = self._catalog

        names = (intent.cpu, intent.mainboard, intent.gpu)
        if any(not name or name.lower() == 'none' for name in names):
            names = _build_models(user_message, catalog) or names

        cpu = resolve_component(names[0], 'CPU', catalog)
        main = resolve_component(names[1], 'MAINBOARD', catalog)
        gpu = resolve_component(names[2], 'GPU', catalog)
        
        if not all((cpu, main, gpu)):
            reply = "Dạ, em chưa tìm thấy đủ CPU, GPU và mainboard trong dữ liệu shop để đánh giá chính xác combo này ạ."
        else:
            reply = _format_review(cpu, main, gpu)

        return ChatResult(
            reply=reply,
            contexts=[],
            metadata={"intent": intent.intent}
        )
