from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery, ProductRecord
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam

class PriceHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, intent: ParsedIntent, route_decision=None) -> ChatResult:
        if intent.intent == "price_calculation":
            return await self._handle_price_calculation(request, intent)
        else:
            return await self._handle_price_check(request, intent)

    async def _handle_price_check(self, request: DomainRequest, intent: ParsedIntent) -> ChatResult:
        # Resolve target
        lookup_term = intent.target_product or ""
        if not lookup_term or lookup_term.strip().lower() == "none":
            for fallback in [intent.cpu, intent.gpu, intent.mainboard]:
                if fallback and fallback.strip().lower() != "none":
                    lookup_term = fallback
                    break
            else:
                lookup_term = request.user_message

        # Retrieve product
        matches = self._catalog.search_products(ProductQuery(
            text=lookup_term,
            category=intent.category or "",
            limit=1
        ))

        if not matches:
            return self._not_found_result(intent)

        product = matches[0]

        evidence = EvidencePackage(
            query=request.user_message,
            intent=intent.intent,
            items=[
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
            ]
        )

        return await self._generate_and_fallback(request, intent, evidence)

    async def _handle_price_calculation(self, request: DomainRequest, intent: ParsedIntent) -> ChatResult:
        # Collect products to lookup
        targets = []
        for term in [intent.cpu, intent.gpu, intent.mainboard, intent.target_product]:
            if term and term.strip().lower() != "none":
                targets.append(term)
                
        if not targets:
            targets = [request.user_message]

        items = []
        total_price = 0
        missing_terms = []

        for term in targets:
            matches = self._catalog.search_products(ProductQuery(text=term, limit=1))
            if not matches:
                missing_terms.append(term)
            else:
                product = matches[0]
                total_price += product.price or 0
                items.append(
                    EvidenceItem(
                        source_id=product.product_id,
                        source_type="product",
                        facts={
                            "product_id": product.product_id,
                            "name": product.name,
                            "price": product.price
                        }
                    )
                )

        if missing_terms:
            return ChatResult(
                reply=f"Dạ em không tìm thấy thông tin cho: {', '.join(missing_terms)} ạ.",
                metadata={"intent": intent.intent}
            )
            
        items.append(
            EvidenceItem(
                source_id="calculation_result",
                source_type="calculation",
                facts={"calculated_total": total_price}
            )
        )

        evidence = EvidencePackage(
            query=request.user_message,
            intent=intent.intent,
            items=items
        )

        return await self._generate_and_fallback(request, intent, evidence)

    async def _generate_and_fallback(self, request: DomainRequest, intent: ParsedIntent, evidence: EvidencePackage) -> ChatResult:
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

    def _not_found_result(self, intent: ParsedIntent) -> ChatResult:
        return ChatResult(
            reply="Dạ hiện tại em chưa tìm thấy mã sản phẩm này trong kho ạ.",
            metadata={"intent": intent.intent}
        )

    def _format_fallback(self, evidence: EvidencePackage) -> ChatResult:
        # Deterministic fallback when generation fails
        if evidence.intent == "price_check":
            product = evidence.items[0]
            price = product.facts.get("price", 0)
            name = product.facts.get("name", "sản phẩm")
            reply = f"Dạ, giá của {name} hiện tại là {format_currency_vietnam(price)} VNĐ ạ."
        else:
            calc_item = next((item for item in evidence.items if item.source_type == "calculation"), None)
            total = calc_item.facts.get("calculated_total", 0) if calc_item else 0
            reply = f"Dạ, tổng giá tiền của các sản phẩm là {format_currency_vietnam(total)} VNĐ ạ."
            
        return ChatResult(
            reply=reply,
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
