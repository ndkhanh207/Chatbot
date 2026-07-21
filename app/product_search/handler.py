from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam
from app.responses import response_renderer, ResponseCode

class ProductSearchHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, intent: ParsedIntent, route_decision=None) -> ChatResult:
        query = self._build_product_query(request.user_message, intent)
        
        matches = self._catalog.search_products(query)
        
        if not matches:
            reply = response_renderer.render(
                ResponseCode.PRODUCT_NOT_FOUND,
                facts={"query": request.user_message}
            )
            return ChatResult(
                reply=reply,
                metadata={"intent": intent.intent}
            )

        items = []
        for product in matches:
            facts = {
                "product_id": product.product_id,
                "name": product.name,
                "price": format_currency_vietnam(product.price),
                "url": product.attributes.get("url", "")
            }
            if product.attributes:
                for k, v in product.attributes.items():
                    if k.lower() not in ("giá", "price", "tên", "name"):
                        facts[k] = v
                
            items.append(
                EvidenceItem(
                    source_id=product.product_id,
                    source_type="product",
                    facts=facts
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
                    "target_product": intent.target_product,
                    "category": intent.category,
                    "cpu": intent.cpu,
                    "gpu": intent.gpu,
                    "mainboard": intent.mainboard,
                    "spec_detail": intent.spec_detail,
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
        header = response_renderer.render(ResponseCode.SEARCH_HEADER)
        lines = [header]
        for item in evidence.items:
            name = item.facts.get("name", "")
            price = item.facts.get("price", 0)
            lines.append(f"- {name}: {format_currency_vietnam(price)} VNĐ")
            
        return ChatResult(
            reply="\n".join(lines),
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
