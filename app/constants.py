import os
from pathlib import Path

# ---------------------------------------------------------------------
# Numeric column definitions (used for data cleaning)
# ---------------------------------------------------------------------
DEFAULT_INT_COLS = ['số lõi', 'khe RAM', 'khe M.2', 'RAM tối đa']
DEFAULT_FLOAT_COLS = ['giá', 'xung cơ bản', 'xung boost', 'chiều dài', 'tdp', 'bộ nhớ']

# Default fill values for missing numeric data
DEFAULT_FILL_VALUES = {col: 0.0 for col in DEFAULT_FLOAT_COLS + DEFAULT_INT_COLS}

# Alias map for field names (used when building search_text)
FIELD_ALIAS_MAP = {
    'tdp': ['tdp', 'điện năng', 'điện năng tiêu thụ', 'công suất tiêu thụ'],
    'xung cơ bản': ['xung cơ bản', 'base clock'],
    'xung boost': ['xung boost', 'boost clock'],
}


FIELD_KEYWORD_ALIASES = {
    'tdp':          ['tdp', 'điện năng', 'điện năng tiêu thụ', 'công suất'],
    'xung cơ bản':  ['xung cơ bản', 'base clock'],
    'xung boost':   ['xung boost', 'boost clock'],
    'bộ nhớ':       ['bộ nhớ', 'memory', 'vram', 'dung lượng vram', 'dung lượng ram card'],
    'socket':       ['socket', 'socket type', 'loại socket'],
    'số lõi':       ['lõi', 'nhân', 'core', 'số lõi', 'mấy nhân'],
    'số luồng':     ['luồng', 'thread', 'số luồng'],
    'đồ họa':       ['đồ họa', 'igpu', 'onboard', 'tích hợp'],
    'RAM tối đa':   ['ram tối đa', 'max ram', 'nhận tối đa', 'bao nhiêu gb ram', 'tối đa bao nhiêu', 'dung lượng ram'],
    'khe RAM':      ['khe ram', 'khe cắm ram', 'mấy khe ram', 'số khe ram', 'mấy khe cắm ram', 'mấy khe'],
    'màu sắc':      ['màu', 'màu sắc', 'phối màu', 'ngoại hình'],
    'interface':    ['interface', 'giao tiếp', 'chuẩn giao tiếp', 'băng thông', 'khe cắm', 'sata'],
    'pcie':         ['pcie', 'khe cắm pcie', 'pci express', 'khe mở rộng', 'băng thông pcie', 'khe cắm card'],
    'lưu trữ':     ['lưu trữ', 'ổ cứng', 'hdd', 'storage', 'cổng lưu trữ'],
    'khe M.2':      ['khe m.2', 'm.2', 'ssd m.2', 'nvme', 'ổ ssd'],
    'kích thước':   ['kích thước', 'form factor', 'atx', 'micro atx', 'matx', 'mini itx'],
    'Ram hỗ trợ':   ['ram hỗ trợ', 'ddr4', 'ddr5', 'loại ram', 'chuẩn ram', 'thế hệ ram'],
}

CPU_TERMS  = ['cpu', 'vi xử lý', 'i3', 'i5', 'i7', 'i9', 'ryzen', 'intel', 'amd']

GPU_TERMS  = ['gpu', 'vga', 'card', 'đồ họa', 'rtx', 'gtx', 'rx', 'nvidia', 'radeon']

MAIN_TERMS = [
    'bo mạch chủ', 'motherboard', 'mainboard', 'main', 
    'form factor', 'atx', 'micro atx', 'matx'
]

CATEGORY_MAP = {"cpu": "CPU", "gpu": "GPU", "mainboard": "MAINBOARD"}