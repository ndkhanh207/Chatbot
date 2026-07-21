from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery, ProductRecord
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam
from app.responses import response_renderer, ResponseCode

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
                            "price": format_currency_vietnam(product.price)
                        }
                    )
                )

        if missing_terms:
            reply = response_renderer.render(
                ResponseCode.MISSING_PRICE_TERMS,
                facts={"terms": ", ".join(missing_terms)}
            )
            return ChatResult(
                reply=reply,
                metadata={"intent": intent.intent}
            )
            
        items.append(
            EvidenceItem(
                source_id="calculation_result",
                source_type="calculation",
                facts={"calculated_total": format_currency_vietnam(total_price)}
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
                    "target_product": intent.target_product,
                    "category": intent.category,
                    "cpu": intent.cpu,
                    "gpu": intent.gpu,
                    "mainboard": intent.mainboard,
                    "spec_detail": intent.spec_detail,
                },
            )

        return self._format_fallback(evidence)

    def _not_found_result(self, intent: ParsedIntent) -> ChatResult:
        reply = response_renderer.render(ResponseCode.PRODUCT_NOT_FOUND)
        return ChatResult(
            reply=reply,
            metadata={"intent": intent.intent}
        )

    def _format_fallback(self, evidence: EvidencePackage) -> ChatResult:
        # Deterministic fallback when generation fails
        if evidence.intent == "price_check":
            product = evidence.items[0]
            price = product.facts.get("price", 0)
            name = product.facts.get("name", "sản phẩm")
            reply = response_renderer.render(
                ResponseCode.PRICE_CHECK_FALLBACK,
                facts={"name": name, "price_formatted": format_currency_vietnam(price)}
            )
        else:
            calc_item = next((item for item in evidence.items if item.source_type == "calculation"), None)
            total = calc_item.facts.get("calculated_total", 0) if calc_item else 0
            reply = response_renderer.render(
                ResponseCode.PRICE_CALCULATION_FALLBACK,
                facts={"total_formatted": format_currency_vietnam(total)}
            )
            
        return ChatResult(
            reply=reply,
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
