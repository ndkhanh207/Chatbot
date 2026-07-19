"""PC Builder routing and state constants."""

BUILD_PC_TRIGGERS = [
    "build pc", "build 1 bộ", "build một bộ", "build bo",
    "xây dựng pc", "tư vấn bộ pc", "tư vấn pc",
    "bộ pc", "cấu hình pc", "dựng pc", "lắp pc",
    "trọn bộ", "bộ máy tính", "cấu hình máy",
    "máy tính tầm", "pc tầm", "máy tính dưới",
    "pc gaming", "máy gaming", "bộ khác", "cấu hình khác",
    "tiệm net", "phòng máy", "quán net", "máy trạm",
    "workstation", "bộ máy", "máy chơi game",
    "bộ pc intel", "bộ pc amd", "pc intel", "pc amd",
    "bộ pc nvidia", "pc nvidia", "pc render", "pc đồ họa", "pc ai",
    "build 1 máy", "build một máy", "build máy", "máy văn phòng", "build theo",
    "nâng cấp", "upgrade", "đang có", "tôi có sẵn", "tôi đang có", "tôi có",
    "build phần còn lại", "phần còn lại", "giữ lại", "tận dụng",
]

BUILD_PC_REGEX_PATTERNS = [
    r"build\s*\d*\s*(bộ|máy|may|pc|cái)",
    r"build\s+\d+\s+\w*",
    r"(tư vấn|gợi ý|ráp|lắp|dựng|xây)\s*(cho\s+tôi\s+)?(bộ|một\s+bộ|pc|máy)",
    r"(bộ|máy|cấu hình)\s*(pc|tính|gaming|văn phòng|render|đồ họa|ai|lập trình)",
    r"(máy|pc|cấu hình)\s*(tầm|dưới|khoảng|từ|giá)\s*\d",
    r"\d+\s*(triệu|tr|m)\b.{0,15}(máy|pc|build|lắp|dựng)",
    r"(lắp|ráp|dựng|xây)\s*(pc|máy|bộ)",
    r"muốn\s*(có\s+)?(một\s+)?(bộ|máy|pc)",
    r"(mua|sắm)\s*(bộ|máy|pc)\s*(mới|ngon|tốt)",
    r"(chơi game|làm đồ họa|lập trình|văn phòng).{0,20}(máy|pc|bộ)",
    r"(máy|pc|bộ).{0,20}(chơi game|làm đồ họa|lập trình|văn phòng)",
]

ADAPTIVE_PENDING = "adaptive_pc_build"
BUDGET_PENDING = "pc_build_budget"
BUILD_CANDIDATE_LIMIT = 5
MAX_CLARIFICATIONS = 2

# STUBS to keep flow.py from crashing on import
BEST_KEYWORDS = []
CHEAPEST_KEYWORDS = []
EXPENSIVE_KEYWORDS = []
PURPOSE_KEYWORD_MAP = {}
ADJUSTMENT_LOCK_KEYWORDS = []
ADJUSTMENT_SWAP_KEYWORDS = []
ADJUSTMENT_BUDGET_KEYWORDS = []
BRAND_SWITCH_KEYWORDS = []
