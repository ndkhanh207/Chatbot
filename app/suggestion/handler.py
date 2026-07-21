from typing import Any
from app.chat.contracts import DomainHandler
from app.chat.models import DomainRequest, ChatResult
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.catalog import ShopCatalog, ProductQuery
from app.catalog.lookup import resolve_component
from app.rag.models import EvidencePackage, EvidenceItem, GroundedAnswerRequest
from app.rag.generator import generate_grounded_answer
from app.compatibility.compat_logic import find_compatible_build
from app.constants import CATEGORY_MAP
from app.utils.format import format_currency_vietnam

class SuggestionHandler:
    def __init__(self, catalog: ShopCatalog):
        self._catalog = catalog

    async def handle(self, request: DomainRequest, intent: ParsedIntent) -> ChatResult:
        candidates = [("cpu", intent.cpu), ("mainboard", intent.mainboard), ("gpu", intent.gpu)]
        owned = [(t, n) for t, n in candidates if n and n.strip().lower() != "none"]
        
        if len(owned) != 1:
            return ChatResult(
                reply="Dạ em chưa rõ anh/chị đang muốn nâng cấp linh kiện nào. Vui lòng cung cấp chính xác 1 linh kiện gốc (VD: 'Tôi đang có main H610, tư vấn giúp tôi CPU') ạ.",
                metadata={"intent": intent.intent}
            )

        have_type, have_name = owned[0]
        
        # Validate logic
        if intent.category and intent.category.strip().lower() == have_type:
            type_display = {"cpu": "CPU", "mainboard": "Mainboard", "gpu": "Card màn hình"}.get(have_type, have_type.capitalize())
            return ChatResult(
                reply=f"Dạ một bộ PC thông thường chỉ dùng một {type_display}, nên em không thể ghép {have_name} với một {type_display} khác được ạ.",
                metadata={"intent": intent.intent}
            )

        supported_categories = ["cpu", "mainboard", "gpu", "vga", "none"]
        if intent.category and intent.category.strip().lower() not in supported_categories:
            return ChatResult(
                reply=f"Dạ hiện tại tính năng gợi ý tự động cho '{intent.category}' chưa được hỗ trợ, em chỉ mới hỗ trợ ghép CPU, Mainboard và VGA thôi ạ.",
                metadata={"intent": intent.intent}
            )

        have_item = resolve_component(have_name, CATEGORY_MAP.get(have_type, have_type.upper()), self._catalog)
        if not have_item:
            return ChatResult(
                reply=f"Dạ em không tìm thấy sản phẩm '{have_name}' trong kho nên chưa thể gợi ý linh kiện tương thích chính xác được ạ.",
                metadata={"intent": intent.intent}
            )

        # Retrieve inventory to match against
        inventory = []
        for category in ("CPU", "MAINBOARD", "GPU"):
            inventory.extend(
                product.as_legacy_dict()
                for product in self._catalog.search_products(
                    ProductQuery(text="", category=category, limit=20) # Limit for perf
                )
            )
            
        build = find_compatible_build(have_type, have_item, inventory, top_k=5)
        
        items = [EvidenceItem(
            source_id=have_item.get("product_id", have_type),
            source_type="product",
            facts=have_item
        )]
        
        for key in ("mainboards", "cpus", "gpus"):
            suggested = build.get(key)
            if suggested:
                for entry in suggested:
                    items.append(EvidenceItem(
                        source_id=entry["item"].get("product_id", key),
                        source_type="product",
                        facts=entry["item"]
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
        reply = "Dạ đây là một số linh kiện tương thích mà em tìm được ạ:\n"
        # Just dump the items except the first one (owned)
        for item in evidence.items[1:]:
            name = item.facts.get("name", "")
            price = item.facts.get("price", 0)
            reply += f"- {name} ({format_currency_vietnam(price)} VNĐ)\n"
            
        return ChatResult(
            reply=reply,
            contexts=[item.source_id for item in evidence.items],
            metadata={"intent": evidence.intent, "fallback": True}
        )
