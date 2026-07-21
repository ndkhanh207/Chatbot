from app.catalog import ShopCatalog
from app.chat.contracts import DomainHandler
from app.price.handler import PriceHandler
from app.product_search.handler import ProductSearchHandler
from app.specification.handler import SpecificationHandler
from app.compatibility.handler import CompatibilityHandler
from app.suggestion.handler import SuggestionHandler
from app.pc_builder.handler import PCBuilderHandler
from app.combo_review.handler import ComboReviewHandler
from app.general_chat.handler import GeneralChatHandler

class HandlerRegistry:
    def __init__(self, handlers: dict[str, DomainHandler]) -> None:
        self._handlers = dict(handlers)

    def get(self, intent: str) -> DomainHandler:
        try:
            return self._handlers[intent]
        except KeyError as error:
            raise LookupError(f"No handler registered for {intent!r}") from error

def create_handler_registry(
    catalog: ShopCatalog,
) -> HandlerRegistry:
    return HandlerRegistry(
        {
            "price_check": PriceHandler(catalog=catalog),
            "price_calculation": PriceHandler(catalog=catalog),
            "general_search": ProductSearchHandler(catalog=catalog),
            "budget_search": ProductSearchHandler(catalog=catalog),
            "specification": SpecificationHandler(catalog=catalog),
            "compatibility": CompatibilityHandler(catalog=catalog),
            "suggestion": SuggestionHandler(catalog=catalog),
            "build_pc": PCBuilderHandler(catalog=catalog),
            "combo_review": ComboReviewHandler(catalog=catalog),
            "none": GeneralChatHandler(),
        }
    )
