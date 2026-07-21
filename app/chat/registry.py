from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
from app.routing.models import HandlerDescriptor


@dataclass(frozen=True, slots=True)
class HandlerRegistration:
    descriptor: HandlerDescriptor
    handler: DomainHandler


class HandlerRegistry:
    def __init__(
        self,
        registrations: list[HandlerRegistration],
    ) -> None:
        self._registrations = tuple(registrations)
        self._handlers = {
            registration.descriptor.name: registration.handler
            for registration in registrations
        }

    def get_handler(
        self,
        name: str,
    ) -> DomainHandler:
        try:
            return self._handlers[name]
        except KeyError as error:
            raise LookupError(f"Unknown handler: {name!r}") from error

    def descriptors(self) -> tuple[HandlerDescriptor, ...]:
        return tuple(
            registration.descriptor
            for registration in self._registrations
        )


from app.pc_builder.models import PcContextRepository

def create_handler_registry(
    catalog: ShopCatalog,
    pc_repository: PcContextRepository,
) -> HandlerRegistry:
    return HandlerRegistry(
        [
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="build_pc",
                    description="Táº¡o, chá»‰nh sá»­a, tiáº¿p tá»¥c hoáº·c tráº£ lá»i cÃ¡c cÃ¢u há»i vá» cáº¥u hÃ¬nh PC hoÃ n chá»‰nh Ä‘ang Ä‘Æ°á»£c rÃ¡p.",
                    supported_operations=(
                        "táº¡o cáº¥u hÃ¬nh má»›i",
                        "thay Ä‘á»•i ngÃ¢n sÃ¡ch",
                        "thay Ä‘á»•i linh kiá»‡n",
                        "thay Ä‘á»•i má»¥c Ä‘Ã­ch",
                        "yÃªu cáº§u cáº¥u hÃ¬nh thay tháº¿",
                        "há»i vá» cáº¥u hÃ¬nh Ä‘Ã£ chá»n",
                    ),
                    stateful=True,
                ),
                handler=PCBuilderHandler(catalog=catalog, repository=pc_repository),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="price",
                    description="Kiá»ƒm tra giÃ¡ sáº£n pháº©m hoáº·c tÃ­nh tá»•ng tiá»n cho cÃ¡c sáº£n pháº©m Ä‘Æ¡n láº».",
                    supported_operations=(
                        "kiá»ƒm tra giÃ¡ sáº£n pháº©m",
                        "tÃ­nh tá»•ng tiá»n sáº£n pháº©m",
                    ),
                    stateful=False,
                ),
                handler=PriceHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="product_search",
                    description="TÃ¬m kiáº¿m cÃ¡c linh kiá»‡n hoáº·c sáº£n pháº©m Ä‘Æ¡n láº» dá»±a trÃªn yÃªu cáº§u chung, ngÃ¢n sÃ¡ch, hoáº·c thÃ´ng sá»‘.",
                    supported_operations=(
                        "tÃ¬m sáº£n pháº©m theo ngÃ¢n sÃ¡ch",
                        "tÃ¬m kiáº¿m sáº£n pháº©m theo tÃªn",
                    ),
                    stateful=False,
                ),
                handler=ProductSearchHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="specification",
                    description="Tráº£ lá»i cÃ¡c cÃ¢u há»i vá» thÃ´ng sá»‘ ká»¹ thuáº­t cá»§a cÃ¡c sáº£n pháº©m Ä‘Æ¡n láº».",
                    supported_operations=("thÃ´ng sá»‘ ká»¹ thuáº­t sáº£n pháº©m",),
                    stateful=False,
                ),
                handler=SpecificationHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="compatibility",
                    description="Kiá»ƒm tra xem cÃ¡c linh kiá»‡n cÃ³ tÆ°Æ¡ng thÃ­ch vá»›i nhau hay khÃ´ng.",
                    supported_operations=(
                        "kiá»ƒm tra tÆ°Æ¡ng thÃ­ch linh kiá»‡n",
                    ),
                    stateful=False,
                ),
                handler=CompatibilityHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="suggestion",
                    description="Gá»£i Ã½ linh kiá»‡n phÃ¹ há»£p khi ngÆ°á»i dÃ¹ng Ä‘Ã£ cÃ³ sáºµn má»™t hoáº·c nhiá»u linh kiá»‡n.",
                    supported_operations=(
                        "gá»£i Ã½ linh kiá»‡n ghÃ©p cÃ¹ng linh kiá»‡n cÃ³ sáºµn",
                    ),
                    stateful=False,
                ),
                handler=SuggestionHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="combo_review",
                    description="ÄÃ¡nh giÃ¡, phÃ¢n tÃ­ch cáº¥u hÃ¬nh PC hoÃ n chá»‰nh cÃ³ sáºµn hoáº·c danh sÃ¡ch linh kiá»‡n cá»‘t lÃµi do ngÆ°á»i dÃ¹ng cung cáº¥p (CPU + GPU + Mainboard).",
                    supported_operations=(
                        "Ä‘Ã¡nh giÃ¡ cáº¥u hÃ¬nh PC ngÆ°á»i dÃ¹ng cung cáº¥p",
                        "phÃ¢n tÃ­ch Ä‘á»™ cÃ¢n báº±ng linh kiá»‡n",
                    ),
                    stateful=False,
                ),
                handler=ComboReviewHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="general_chat",
                    description="Xá»­ lÃ½ giao tiáº¿p thÃ´ng thÆ°á»ng, chÃ o há»i, cÃ¡c cÃ¢u há»i khÃ´ng liÃªn quan, vÃ  lÃ m phÆ°Æ¡ng Ã¡n dá»± phÃ²ng.",
                    supported_operations=(
                        "chÃ o há»i",
                        "giao tiáº¿p thÃ´ng thÆ°á»ng",
                        "cÃ¢u há»i chung chung",
                    ),
                    stateful=False,
                ),
                handler=GeneralChatHandler(),
            ),
        ]
    )
