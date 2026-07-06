# app/pc_builder/pc_constants.py
"""
Chứa toàn bộ các từ khóa, mapping dùng chung cho module PC Builder.
"""
import re

# ──────────────────────────────────────────────
# Từ khóa detect intent "build PC" — Literal (fallback nhanh)
# ──────────────────────────────────────────────
BUILD_PC_TRIGGERS = [
    'build pc', 'build 1 bộ', 'build một bộ', 'build bo',
    'xây dựng pc', 'tư vấn bộ pc', 'tư vấn pc',
    'bộ pc', 'cấu hình pc', 'dựng pc', 'lắp pc',
    'trọn bộ', 'bộ máy tính', 'cấu hình máy',
    'máy tính tầm', 'pc tầm', 'máy tính dưới',
    'pc gaming', 'máy gaming', 'bộ khác', 'cấu hình khác',
    # Thêm các trường hợp máy đặc thù
    'tiệm net', 'phòng máy', 'quán net', 'máy trạm',
    'workstation', 'bộ máy', 'máy chơi game',
    'bộ pc intel', 'bộ pc amd', 'pc intel', 'pc amd',
    'bộ pc nvidia', 'pc nvidia', 'pc render', 'pc đồ họa', 'pc ai',
    'build 1 máy', 'build một máy', 'build máy', 'máy văn phòng', 'build theo',
    'nâng cấp', 'upgrade', 'đang có', 'tôi có sẵn', 'tôi đang có', 'tôi có',
    'build phần còn lại', 'phần còn lại', 'giữ lại', 'tận dụng'
]

# ──────────────────────────────────────────────
# Từ khóa điều chỉnh PC (Multi-turn adjustments)
# ──────────────────────────────────────────────
ADJUSTMENT_LOCK_KEYWORDS = ['giữ nguyên', 'đừng đổi', 'giữ lại', 'không đổi', 'không muốn đổi', 'không cần đổi', 'ko đổi', 'giữ', 'chốt', 'chọn']
ADJUSTMENT_SWAP_KEYWORDS = ['đổi sang', 'đổi', 'thay bằng', 'chuyển sang', 'nâng cấp', 'lấy']
ADJUSTMENT_PRIORITY_KEYWORDS = ['ưu tiên', 'tập trung', 'đổ tiền', 'dồn tiền', 'tối ưu']
ADJUSTMENT_BUDGET_KEYWORDS = ['tăng ngân sách', 'giảm', 'thôi', 'còn', 'rẻ hơn', 'đắt hơn', 'lên', 'xuống']
BRAND_SWITCH_KEYWORDS = ['đổi sang amd', 'quay lại amd', 'đổi sang intel', 'quay lại intel', 'đổi sang nvidia', 'chuyển sang amd', 'chuyển sang intel', 'chuyển sang nvidia']

# Regex pattern linh hoạt hơn cho build PC — bắt nhiều biến thể tự nhiên
BUILD_PC_REGEX_PATTERNS = [
    r'build\s*\d*\s*(bộ|máy|may|pc|cái)',                     # "build 1 bộ", "build 1 may", "build máy"
    r'build\s+\d+\s+\w*',                                      # "build 1 may", "build 2 bo" (bất kỳ từ theo sau)
    r'(tư vấn|gợi ý|ráp|lắp|dựng|xây)\s*(cho\s+tôi\s+)?(bộ|một\s+bộ|pc|máy)',
    r'(bộ|máy|cấu hình)\s*(pc|tính|gaming|văn phòng|render|đồ họa|ai|lập trình)',
    r'(máy|pc|cấu hình)\s*(tầm|dưới|khoảng|từ|giá)\s*\d',   # "máy tầm 20 triệu"
    r'\d+\s*(triệu|tr|m)\b.{0,15}(máy|pc|build|lắp|dựng)',   # "20 triệu build máy"
    r'(lắp|ráp|dựng|xây)\s*(pc|máy|bộ)',
    r'muốn\s*(có\s+)?(một\s+)?(bộ|máy|pc)',                   # "muốn có một bộ máy"
    r'(mua|sắm)\s*(bộ|máy|pc)\s*(mới|ngon|tốt)',              # "mua bộ máy mới"
    r'(chơi game|làm đồ họa|lập trình|văn phòng).{0,20}(máy|pc|bộ)',
    r'(máy|pc|bộ).{0,20}(chơi game|làm đồ họa|lập trình|văn phòng)',
]


# ──────────────────────────────────────────────
# Bảng ánh xạ mục đích → từ khóa trong Build_Notes
# ──────────────────────────────────────────────
PURPOSE_KEYWORD_MAP = {
    'game aaa': [
        'game aaa', 'triple aaa', 'chơi game aaa', '4k/2k',
        'chơi game 4k', 'game nặng', 'chơi game ở 4k',
        'game triple a', 'tựa game nặng', 'game 4k', 'ultra setting',
        'setting cao', 'frame cao', 'fps cao', 'cyberpunk', 'wukong',
    ],

    'game': [
        'chơi game', 'game', 'esports', 'gaming', 'stream game',
        'game online', 'game thủ', 'play game', 'game fps', 'game moba',
        'liên minh', 'valorant', 'csgo', 'cs2', 'pubg', 'fortnite',
        'chơi lol', 'chơi val', 'game cũ', 'game nhẹ', 'black myth',
        'wukong', 'gta', 'gta vi', 'gta 6', 'league of legends', 'dota',
        'minecraft', 'overwatch', 'counter-strike',
    ],
    'render': [
        'render 3d', 'render', 'dựng phim', 'blender', 'maya',
        'cinema 4d', 'c4d', '3ds max', 'dựng 3d', 'animation',
        'làm phim', 'video editing', 'edit video', 'premiere', 'after effects',
        'davinci', '4k edit', 'cut video', 'chỉnh sửa video'
    ],
    'đồ họa': [
        'render 3d', 'dựng phim', 'đồ họa kỹ thuật', 'autodesk',
        'photoshop', 'illustrator', 'đồ họa', 'thiết kế', 'design',
        'đồ họa 2d', 'graphic design', 'in ấn', 'làm design', 'lightroom'
    ],
    'lập trình': [
        'lập trình', 'máy ảo', 'data science', 'xử lý dữ liệu', 'code', 'dev',
        'developer', 'coding', 'software', 'back end', 'frontend', 'fullstack',
        'docker', 'kubernetes', 'chạy máy ảo', 'virtual machine', 'vm',
        'compile', 'build code', 'ide', 'vscode', 'java', 'spring', 'spring boot',
        'android studio', 'android', 'kotlin', 'flutter', 'mobile', 'backend',
        'node.js', 'react', 'nextjs'
    ],
    'văn phòng': [
        'văn phòng', 'word', 'excel', 'học tập', 'lướt web', 'cơ bản', 'tiệm net', 'quán net',
        'chung chung', 'bình thường', 'giải trí nhẹ', 'không có nhu cầu đặc biệt', 'đa dụng',
        'học online', 'zoom', 'teams', 'google meet', 'powerpoint', 'google docs',
        'office', 'email', 'xem phim', 'nghe nhạc', 'youtube', 'sinh viên',
        'học sinh', 'nhẹ nhàng', 'cơ bản thôi', 'dùng bình thường',
    ],
    'ai': [
        'deep learning', 'huấn luyện ai', 'ai', 'machine learning',
        'ml', 'dl', 'train model', 'training model',
        'data science', 'xử lý dữ liệu nặng', 'data nặng', 'workstation ai',
        'neural network', 'pytorch', 'tensorflow',
        'llm', 'stable diffusion', 'hugging face', 'cuda training',
    ],
    'stream': [
        'stream game', 'stream đa nền tảng', 'stream',
        'livestream', 'streaming', 'obs', 'obs studio',
        'twitch', 'youtube live', 'phát trực tiếp',
    ],
    'video editing': [
        'premiere', 'edit video', 'davinci', 'after effects', 'video editing',
        '4k edit', 'cut video', 'chỉnh sửa video'
    ]
}

# ──────────────────────────────────────────────
# Brand filter mapping
# ──────────────────────────────────────────────
CPU_BRAND_MAP = {
    'intel': 'Intel',
    'amd':   'AMD',
}
GPU_BRAND_MAP = {
    'nvidia': 'Nvidia',
    'amd':    'AMD',
    'intel':  'Intel',  # Intel Arc
}

PERIPHERAL_BRAND_MAP = {
    'asus': 'ASUS',
    'msi': 'MSI',
    'gigabyte': 'Gigabyte',
    'corsair': 'Corsair'
}

# ──────────────────────────────────────────────
# Từ khóa "tốt nhất / rẻ nhất / đắt nhất"
# ──────────────────────────────────────────────
BEST_KEYWORDS    = ['tốt nhất', 'ngon nhất', 'mạnh nhất', 'đỉnh nhất', 'cao cấp nhất']
CHEAPEST_KEYWORDS = ['rẻ nhất', 'giá thấp nhất', 'thấp nhất', 'tiết kiệm nhất', 'bèo nhất', 'the cheapest']
EXPENSIVE_KEYWORDS = ['đắt nhất', 'mắc nhất', 'giá cao nhất', 'cao nhất', 'the most expensive']

# ──────────────────────────────────────────────
# Regex nhận diện câu hỏi ngân sách từ AI (thay thế list cứng)
# Dùng để detect: "AI vừa hỏi ngân sách chưa?"
# ──────────────────────────────────────────────
AI_BUDGET_REGEX_PATTERNS = [
    r'(dự định|muốn|có thể|định)\s*(đầu tư|chi|bỏ ra|chi ra|tiêu)',
    r'tầm\s*(giá|tiền|bao nhiêu)',
    r'ngân\s*sách',
    r'bao nhiêu\s*(tiền|vậy|ạ|nhỉ)?',
    r'(tầm|khoảng|giá)\s*(bao nhiêu|nào)',
    r'(ngân sách|budget)',
    r'đầu tư.{0,15}(bao nhiêu|tiền|triệu)',
    r'giá\s*(tầm|khoảng|dưới|từ)',
]

# Giữ lại list cứng để dùng nhanh (AND với regex ở trên)
AI_BUDGET_KEYWORDS = ['ngân sách', 'tầm giá', 'bao nhiêu tiền', 'đầu tư cho bộ pc', 'dự định đầu tư', 'bao nhiêu ạ', 'khoảng bao nhiêu', 'đầu tư khoảng']
AI_PURPOSE_KEYWORDS = ['để làm gì', 'mục đích gì', 'nhu cầu của bạn', 'dùng để làm', 'chủ yếu để', 'chủ yếu dùng', 'mục đích sử dụng']
AI_BUILD_CONTEXT_KEYWORDS = AI_BUDGET_KEYWORDS + AI_PURPOSE_KEYWORDS + ['tư vấn bộ pc']
