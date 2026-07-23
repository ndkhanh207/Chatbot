from app.chat.models import DomainRequest, ChatResult
from app.core.extraction.extractor import ExtractedEntities
from app.catalog import ShopCatalog, ProductQuery
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.utils.format import format_currency_vietnam
from app.responses import response_renderer, ResponseCode

class PriceHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, entities: ExtractedEntities, route_decision=None) -> ChatResult:
        if len(self._price_targets(entities)) > 1:
            return await self._handle_price_calculation(request, entities)
        return await self._handle_price_check(request, entities)

    @staticmethod
    def _price_targets(entities: ExtractedEntities) -> list[str]:
        targets = []
        seen = set()
        for term in (entities.cpu, entities.gpu, entities.mainboard, entities.target_product):
            if not term:
                continue
            key = " ".join(term.casefold().replace("-", " ").split())
            if key not in seen:
                seen.add(key)
                targets.append(term)
        return targets

    async def _handle_price_check(self, request: DomainRequest, entities: ExtractedEntities) -> ChatResult:
        # Resolve target
        lookup_term = entities.target_product or ""
        if not lookup_term or lookup_term.strip().lower() == "none":
            for fallback in [entities.cpu, entities.gpu, entities.mainboard]:
                if fallback and fallback.strip().lower() != "none":
                    lookup_term = fallback
                    break
            else:
                lookup_term = request.user_message

        # Retrieve product
        matches = self._catalog.search_products(ProductQuery(
            text=lookup_term,
            category=entities.category or "",
            limit=1
        ))

        if not matches:
            return self._not_found_result(entities)

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
            intent=entities.intent,
            items=[
                EvidenceItem(
                    source_id=product.product_id,
                    source_type="product",
                    facts=facts
                )
            ]
        )

        return await self._generate_and_fallback(request, entities, evidence)

    async def _handle_price_calculation(self, request: DomainRequest, entities: ExtractedEntities) -> ChatResult:
        # Collect products to lookup
        targets = self._price_targets(entities)
                
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
                metadata={"intent": entities.intent}
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
            intent=entities.intent,
            items=items
        )

        return await self._generate_and_fallback(request, entities, evidence)

    async def _generate_and_fallback(self, request: DomainRequest, entities: ExtractedEntities, evidence: EvidencePackage) -> ChatResult:
        generation = await generate_grounded_answer(
            GroundedAnswerRequest(
                user_message=request.user_message,
                intent=entities.intent,
                evidence=evidence
            )
        )

        if generation.ok and generation.value:
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

        return self._format_fallback(evidence)

    def _not_found_result(self, entities: ExtractedEntities) -> ChatResult:
        reply = response_renderer.render(ResponseCode.PRODUCT_NOT_FOUND)
        return ChatResult(
            reply=reply,
            metadata={"intent": entities.intent}
        )

    def _format_fallback(self, evidence: EvidencePackage) -> ChatResult:
        # Deterministic fallback when generation fails
        calc_item = next(
            (item for item in evidence.items if item.source_type == "calculation"),
            None,
        )
        if calc_item is None:
            product = evidence.items[0]
            price = product.facts.get("price", 0)
            name = product.facts.get("name", "sản phẩm")
            reply = response_renderer.render(
                ResponseCode.PRICE_CHECK_FALLBACK,
                facts={"name": name, "price_formatted": price}
            )
        else:
            total = calc_item.facts.get("calculated_total", 0)
            reply = response_renderer.render(
                ResponseCode.PRICE_CALCULATION_FALLBACK,
                facts={"total_formatted": total}
            )
            
        return ChatResult(
            reply=reply,
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
