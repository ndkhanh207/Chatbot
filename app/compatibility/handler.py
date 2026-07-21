from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery
from app.catalog.lookup import resolve_component
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.compatibility.compat_logic import check_cpu_main_compat, check_gpu_main_compat

class CompatibilityHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, intent: ParsedIntent, route_decision=None) -> ChatResult:
        # Resolve components via legacy helper or ShopCatalog
        cpu = resolve_component(intent.cpu or "", "CPU", self._catalog) if intent.cpu else None
        main = resolve_component(intent.mainboard or "", "MAINBOARD", self._catalog) if intent.mainboard else None
        gpu = resolve_component(intent.gpu or "", "GPU", self._catalog) if intent.gpu else None

        if not any([cpu, main, gpu]):
            return ChatResult(
                reply="Dạ thông tin linh kiện anh/chị cung cấp chưa đủ rõ ràng hoặc không có trong kho. Xin vui lòng cung cấp đúng tên linh kiện để em kiểm tra tương thích ạ.",
                metadata={"intent": intent.intent}
            )

        cpu_main = check_cpu_main_compat(cpu, main) if cpu and main else None
        gpu_main = check_gpu_main_compat(gpu, main) if gpu and main else None
        
        if cpu_main and cpu_main["status"] == "incompatible":
            overall = "incompatible"
        elif cpu_main or gpu_main:
            statuses = [check["status"] for check in (cpu_main, gpu_main) if check]
            overall = "compatible" if all(status == "compatible" for status in statuses) else "unknown"
        elif cpu and gpu:
            overall = "not_directly_checkable"
        else:
            overall = "unknown"

        items = []
        if cpu:
            items.append(EvidenceItem(
                source_id=cpu.get("product_id", "cpu"),
                source_type="product",
                facts=cpu
            ))
        if main:
            items.append(EvidenceItem(
                source_id=main.get("product_id", "main"),
                source_type="product",
                facts=main
            ))
        if gpu:
            items.append(EvidenceItem(
                source_id=gpu.get("product_id", "gpu"),
                source_type="product",
                facts=gpu
            ))

        items.append(EvidenceItem(
            source_id="compatibility_report",
            source_type="compatibility_report",
            facts={
                "overall_status": overall,
                "cpu_main_check": cpu_main,
                "gpu_main_check": gpu_main,
            }
        ))

        evidence = EvidencePackage(
            query=request.user_message,
            intent=intent.intent,
            items=items
        )

        generation = await generate_grounded_answer(
            GroundedAnswerRequest(
                user_message=request.user_message,
                intent=intent.intent,
                evidence=evidence
            )
        )

        if generation.ok and generation.value:
            reply = generation.value.answer
                
            return ChatResult(
                reply=reply,
                contexts=[item.source_id for item in evidence.items],
                metadata={
                    "intent": intent.intent,
                    "source_ids": generation.value.used_source_ids,
                },
            )

        return ChatResult(
            reply="Dạ hệ thống đang xử lý chậm nên chưa thể kiểm tra tương thích. Bạn vui lòng thử lại sau nhé.",
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
