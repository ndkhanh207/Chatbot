# pc_build_advisor.py
"""
Module tư vấn bộ PC trọn gói (CPU + GPU + Mainboard).
Tìm kiếm bộ PC phù hợp nhất dựa trên ngân sách và mục đích sử dụng.
Đóng vai trò Facade: Export lại các hàm từ module con để không làm gãy code cũ.
"""

# Re-export các hằng số
from .constants import (
    BUILD_PC_TRIGGERS, PURPOSE_KEYWORD_MAP
)

# Re-export các hàm extraction
from .extractor import (
    detect_build_pc_intent
)

from .formatter import format_build_context

__all__ = [
    # constants
    "BUILD_PC_TRIGGERS", "PURPOSE_KEYWORD_MAP",
    # extractor
    "detect_build_pc_intent",
    # formatter
    "format_build_context"
]
