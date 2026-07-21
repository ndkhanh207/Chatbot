from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer

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
            return ChatResult(
                reply="Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho ạ.",
                metadata={"intent": intent.intent}
            )

        product = matches[0]

        facts: dict[str, Any] = {
            "product_id": product.product_id,
            "name": product.name,
            "category": product.category,
            "price": product.price,
        }
        
        # Merge attributes into facts
        if product.attributes:
            facts.update(product.attributes)

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
                },
            )

        return self._format_fallback(evidence)

    def _format_fallback(self, evidence: EvidencePackage) -> ChatResult:
        product = evidence.items[0]
        name = product.facts.get("name", "sản phẩm")
        
        reply = f"Dạ đây là thông tin kỹ thuật của {name}. Do lỗi kết nối, em chỉ có thể cung cấp nguyên mẫu hệ thống: {product.facts}"
            
        return ChatResult(
            reply=reply,
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
