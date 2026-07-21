from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam

class ProductSearchHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, intent: ParsedIntent) -> ChatResult:
        query = self._build_product_query(request.user_message, intent)
        
        matches = self._catalog.search_products(query)
        
        if not matches:
            return ChatResult(
                reply="Dạ hiện tại cửa hàng chưa có sản phẩm nào phù hợp với yêu cầu của anh/chị ạ.",
                metadata={"intent": intent.intent}
            )

        items = []
        for product in matches:
            items.append(
                EvidenceItem(
                    source_id=product.product_id,
                    source_type="product",
                    facts={
                        "product_id": product.product_id,
                        "name": product.name,
                        "price": product.price,
                        "url": product.attributes.get("url", "")
                    }
                )
            )

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
            return ChatResult(
                reply=generation.value.answer,
                contexts=[item.source_id for item in evidence.items],
                metadata={
                    "intent": intent.intent,
                    "source_ids": generation.value.used_source_ids,
                },
            )

        return self._format_fallback(evidence)

    def _build_product_query(self, message: str, intent: ParsedIntent) -> ProductQuery:
        return ProductQuery(
            text=message,
            category=intent.category or "",
            price_max=(
                int(intent.budget_amount)
                if intent.intent == "budget_search" and getattr(intent, 'budget_amount', 0) > 0
                else None
            ),
            limit=5,
        )

    def _format_fallback(self, evidence: EvidencePackage) -> ChatResult:
        lines = ["Dạ em tìm thấy các sản phẩm sau:"]
        for item in evidence.items:
            name = item.facts.get("name", "")
            price = item.facts.get("price", 0)
            lines.append(f"- {name}: {format_currency_vietnam(price)} VNĐ")
            
        return ChatResult(
            reply="\n".join(lines),
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
