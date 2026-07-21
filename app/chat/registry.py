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
                    description="Tạo, chỉnh sửa, tiếp tục hoặc trả lời các câu hỏi về cấu hình PC hoàn chỉnh đang được ráp.",
                    supported_operations=(
                        "tạo cấu hình mới",
                        "thay đổi ngân sách",
                        "thay đổi linh kiện",
                        "thay đổi mục đích",
                        "yêu cầu cấu hình thay thế",
                        "hỏi về cấu hình đã chọn",
                    ),
                    stateful=True,
                ),
                handler=PCBuilderHandler(catalog=catalog, repository=pc_repository),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="price",
                    description="Kiểm tra giá sản phẩm hoặc tính tổng tiền cho các sản phẩm đơn lẻ.",
                    supported_operations=(
                        "kiểm tra giá sản phẩm",
                        "tính tổng tiền sản phẩm",
                    ),
                    stateful=False,
                ),
                handler=PriceHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="product_search",
                    description="Tìm kiếm các linh kiện hoặc sản phẩm đơn lẻ dựa trên yêu cầu chung, ngân sách, hoặc thông số.",
                    supported_operations=(
                        "tìm sản phẩm theo ngân sách",
                        "tìm kiếm sản phẩm theo tên",
                    ),
                    stateful=False,
                ),
                handler=ProductSearchHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="specification",
                    description="Trả lời các câu hỏi về thông số kỹ thuật của các sản phẩm đơn lẻ.",
                    supported_operations=("thông số kỹ thuật sản phẩm",),
                    stateful=False,
                ),
                handler=SpecificationHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="compatibility",
                    description="Kiểm tra xem các linh kiện có tương thích với nhau hay không.",
                    supported_operations=(
                        "kiểm tra tương thích linh kiện",
                    ),
                    stateful=False,
                ),
                handler=CompatibilityHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="suggestion",
                    description="Gợi ý linh kiện phù hợp khi người dùng đã có sẵn một hoặc nhiều linh kiện.",
                    supported_operations=(
                        "gợi ý linh kiện ghép cùng linh kiện có sẵn",
                    ),
                    stateful=False,
                ),
                handler=SuggestionHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="combo_review",
                    description="Đánh giá, phân tích cấu hình PC hoàn chỉnh có sẵn hoặc danh sách linh kiện cốt lõi do người dùng cung cấp (CPU + GPU + Mainboard).",
                    supported_operations=(
                        "đánh giá cấu hình PC người dùng cung cấp",
                        "phân tích độ cân bằng linh kiện",
                    ),
                    stateful=False,
                ),
                handler=ComboReviewHandler(catalog=catalog),
            ),
            HandlerRegistration(
                descriptor=HandlerDescriptor(
                    name="general_chat",
                    description="Xử lý giao tiếp thông thường, chào hỏi, các câu hỏi không liên quan, và làm phương án dự phòng.",
                    supported_operations=(
                        "chào hỏi",
                        "giao tiếp thông thường",
                        "câu hỏi chung chung",
                    ),
                    stateful=False,
                ),
                handler=GeneralChatHandler(),
            ),
        ]
    )
