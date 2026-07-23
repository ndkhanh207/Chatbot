from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.extraction.extractor import ExtractedEntities
from app.catalog import ShopCatalog
from app.catalog.lookup import resolve_component
from app.rag.generator import generate_grounded_answer
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.compatibility.compat_logic import check_cpu_main_compat, check_gpu_main_compat
from app.compatibility.compat_format import format_compatibility_reply
from app.responses import response_renderer, ResponseCode
from app.utils.format import get_field

class CompatibilityHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, entities: ExtractedEntities, route_decision=None) -> ChatResult:
        cpu = resolve_component(entities.cpu, "CPU", self._catalog) if entities.cpu else None
        main = resolve_component(entities.mainboard, "MAINBOARD", self._catalog) if entities.mainboard else None
        gpu = resolve_component(entities.gpu, "GPU", self._catalog) if entities.gpu else None

        if not any([cpu, main, gpu]):
            reply = response_renderer.render(ResponseCode.COMPATIBILITY_MISSING_INFO)
            return ChatResult(
                reply=reply,
                metadata={"intent": entities.intent}
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

        report = {
            "overall_status": overall,
            "component_models": {
                "cpu": get_field(cpu, "name", "tên") if cpu else None,
                "mainboard": get_field(main, "name", "tên") if main else None,
                "gpu": get_field(gpu, "name", "tên") if gpu else None,
            },
            "cpu_main_check": cpu_main,
            "gpu_main_check": gpu_main,
        }
        items.append(EvidenceItem(
            source_id="compatibility_report",
            source_type="compatibility_report",
            facts=report,
        ))

        evidence = EvidencePackage(
            query=request.user_message,
            intent=entities.intent,
            items=items
        )

        generation = await generate_grounded_answer(GroundedAnswerRequest(
            user_message=request.user_message,
            intent=entities.intent,
            evidence=evidence,
        ))
        valid_generation = bool(
            generation.ok
            and generation.value
            and generation.value.grounded_status == overall
        )
        reply = (
            generation.value.answer
            if valid_generation and generation.value
            else format_compatibility_reply(report)
        )
        context = evidence.model_dump_json(indent=2)

        return ChatResult(
            reply=reply,
            contexts=[context],
            metadata={
                "intent": entities.intent,
                "source_ids": [item.source_id for item in evidence.items],
                "fallback": not valid_generation,
                "target_product": entities.target_product,
                "category": entities.category,
                "cpu": entities.cpu,
                "gpu": entities.gpu,
                "mainboard": entities.mainboard,
                "spec_detail": entities.spec_detail,
            },
        )
