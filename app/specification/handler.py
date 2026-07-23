from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.extraction.extractor import ExtractedEntities
from app.catalog import ShopCatalog, ProductQuery
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam
from app.specification.field_resolver import has_requested_spec_fact
class SpecificationHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, entities: ExtractedEntities, route_decision=None) -> ChatResult:
        lookup_term = entities.target_product or request.user_message

        # Fallback to specific component if target_product is empty
        if not entities.target_product or entities.target_product.strip().lower() == "none":
            for fallback in [entities.cpu, entities.gpu, entities.mainboard]:
                if fallback and fallback.strip().lower() != "none":
                    lookup_term = fallback
                    break

        matches = self._catalog.search_products(ProductQuery(
            text=lookup_term,
            category=entities.category or "",
            limit=1
        ))

        if not matches:
            from app.responses import response_renderer, ResponseCode
            reply = response_renderer.render(
                ResponseCode.PRODUCT_NOT_FOUND,
                facts={"query": lookup_term}
            )
            return ChatResult(
                reply=reply,
                metadata={"intent": entities.intent}
            )

        product = matches[0]

        facts: dict[str, Any] = {
            "product_id": product.product_id,
            "name": product.name,
            "category": product.category,
            "price": format_currency_vietnam(product.price),
        }
        
        # Merge attributes into facts
        if product.attributes:
            for k, v in product.attributes.items():
                if k.lower() not in ("giá", "price", "tên", "name", "category"):
                    facts[k] = v

        if entities.spec_detail and not has_requested_spec_fact(facts, entities.spec_detail):
            from app.responses import response_renderer, ResponseCode
            return ChatResult(
                reply=response_renderer.render(
                    ResponseCode.SPECIFICATION_DETAIL_UNAVAILABLE,
                    facts={"detail": entities.spec_detail, "name": product.name},
                ),
                contexts=[product.product_id],
                metadata={
                    "intent": entities.intent,
                    "target_product": entities.target_product,
                    "category": entities.category,
                    "spec_detail": entities.spec_detail,
                },
            )

        evidence = EvidencePackage(
            query=request.user_message,
            intent=entities.intent,
            items=[
                EvidenceItem(
                    source_id=product.product_id,
                    source_type="product",
                    facts=facts
                )
            ]
        )

        generation = await generate_grounded_answer(
            GroundedAnswerRequest(
                user_message=(
                    f"{request.user_message}\nRequested detail: {entities.spec_detail}"
                    if entities.spec_detail
                    else request.user_message
                ),
                intent=entities.intent,
                evidence=evidence
            )
        )

        if (
            generation.ok
            and generation.value
            and product.product_id in generation.value.used_source_ids
        ):
            return ChatResult(
                reply=generation.value.answer,
                contexts=[item.source_id for item in evidence.items],
                metadata={
                    "intent": entities.intent,
                    "source_ids": generation.value.used_source_ids,
                    "target_product": entities.target_product,
                    "category": entities.category,
                    "cpu": entities.cpu,
                    "gpu": entities.gpu,
                    "mainboard": entities.mainboard,
                    "spec_detail": entities.spec_detail,
                },
            )

        if generation.ok and generation.value and entities.spec_detail:
            from app.responses import response_renderer, ResponseCode
            return ChatResult(
                reply=response_renderer.render(
                    ResponseCode.SPECIFICATION_DETAIL_UNAVAILABLE,
                    facts={"detail": entities.spec_detail, "name": product.name},
                ),
                contexts=[product.product_id],
                metadata={
                    "intent": entities.intent,
                    "target_product": entities.target_product,
                    "category": entities.category,
                    "spec_detail": entities.spec_detail,
                },
            )

        return self._format_fallback(evidence)

    def _format_fallback(self, evidence: EvidencePackage) -> ChatResult:
        product = evidence.items[0]
        name = product.facts.get("name", "sản phẩm")
        
        from app.responses import response_renderer, ResponseCode
        reply = response_renderer.render(
            ResponseCode.SPECIFICATION_FALLBACK,
            facts={"name": name, "facts": product.facts}
        )
            
        return ChatResult(
            reply=reply,
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
