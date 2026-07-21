from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam
class SpecificationHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, intent: ParsedIntent, route_decision=None) -> ChatResult:
        lookup_term = intent.target_product or request.user_message

        # Fallback to specific component if target_product is empty
        if not intent.target_product or intent.target_product.strip().lower() == "none":
            for fallback in [intent.cpu, intent.gpu, intent.mainboard]:
                if fallback and fallback.strip().lower() != "none":
                    lookup_term = fallback
                    break

        matches = self._catalog.search_products(ProductQuery(
            text=lookup_term,
            category=intent.category or "",
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
                metadata={"intent": intent.intent}
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

        evidence = EvidencePackage(
            query=request.user_message,
            intent=intent.intent,
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
                user_message=request.user_message,
                intent=intent.intent,
                evidence=evidence
            )
        )

        if generation.ok and generation.value:
            return ChatResult(
                reply=generation.value.answer,
                contexts=[item.source_id for item in evidence.items],
                metadata={
                    "intent": intent.intent,
                    "source_ids": generation.value.used_source_ids,
                    "target_product": intent.target_product,
                    "category": intent.category,
                    "cpu": intent.cpu,
                    "gpu": intent.gpu,
                    "mainboard": intent.mainboard,
                    "spec_detail": intent.spec_detail,
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
