# app/pc_builder/pc_constants.py
"""
Chứa toàn bộ các từ khóa, mapping dùng chung cho module PC Builder.
"""

# ──────────────────────────────────────────────
# Từ khóa detect intent "build PC"
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
    'build 1 máy', 'build một máy', 'build máy', 'máy văn phòng',
    'nâng cấp', 'upgrade', 'đang có', 'tôi có sẵn', 'tôi đang có', 'tôi có',
    'build phần còn lại', 'phần còn lại', 'giữ lại', 'tận dụng'
]

# ──────────────────────────────────────────────
# Bảng ánh xạ mục đích → từ khóa trong Build_Notes
# ──────────────────────────────────────────────
PURPOSE_KEYWORD_MAP = {
    'game aaa': [
        'game aaa', 'triple aaa', 'chơi game aaa', '4k/2k',
        'chơi game 4k', 'game nặng', 'chơi game ở 4k',
    ],
    'game':    ['chơi game', 'game', 'esports', 'gaming', 'stream game', 'valorant', 'cs2', 'counter-strike', 'black myth', 'wukong', 'gta', 'gta vi', 'gta 6', 'fortnite', 'lol', 'league of legends', 'dota', 'pubg', 'minecraft', 'overwatch'],
    'render':  ['render 3d', 'render', 'dựng phim', 'blender', 'maya'],
    'đồ họa': ['render 3d', 'dựng phim', 'đồ họa kỹ thuật', 'autodesk', 'photoshop', 'illustrator', 'lightroom'],
    'lập trình': ['lập trình', 'máy ảo', 'data science', 'xử lý dữ liệu', 'code', 'dev', 'java', 'spring', 'spring boot', 'android studio', 'android', 'kotlin', 'flutter', 'mobile', 'backend', 'frontend', 'node.js', 'react', 'nextjs'],
    'văn phòng': [
        'văn phòng', 'word', 'excel', 'học tập', 'lướt web', 'cơ bản', 'tiệm net', 'quán net',
        'chung chung', 'bình thường', 'giải trí nhẹ', 'không có nhu cầu đặc biệt', 'đa dụng'
    ],
    'ai': [
        'deep learning', 'huấn luyện ai', 'ai', 'machine learning',
        'ml', 'dl', 'train model', 'training model',
        'data science', 'xử lý dữ liệu nặng', 'workstation ai',
        'neural network', 'pytorch', 'tensorflow',
    ],
    'video editing': ['premiere', 'edit video', 'davinci', 'after effects', 'video editing', '4k edit', 'cut video', 'chỉnh sửa video'],
    'stream':  ['stream game', 'stream đa nền tảng', 'stream'],
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
# Từ khóa "tốt nhất / rẻ nhất"
# ──────────────────────────────────────────────
BEST_KEYWORDS    = ['tốt nhất', 'ngon nhất', 'mạnh nhất', 'đỉnh nhất', 'cao cấp nhất']
CHEAPEST_KEYWORDS = ['rẻ nhất', 'giá thấp nhất', 'thấp nhất', 'tiết kiệm nhất', 'bèo nhất']

# ──────────────────────────────────────────────
# Từ khóa nhận diện câu hỏi từ AI
# ──────────────────────────────────────────────
AI_BUDGET_KEYWORDS = ['ngân sách', 'tầm giá', 'bao nhiêu tiền', 'đầu tư cho bộ pc', 'dự định đầu tư']
AI_PURPOSE_KEYWORDS = ['để làm gì', 'mục đích gì', 'nhu cầu của bạn']
AI_BUILD_CONTEXT_KEYWORDS = AI_BUDGET_KEYWORDS + AI_PURPOSE_KEYWORDS + ['tư vấn bộ pc']
