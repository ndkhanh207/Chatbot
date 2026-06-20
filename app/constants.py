import os
from pathlib import Path

# ---------------------------------------------------------------------
# Numeric column definitions (used for data cleaning)
# ---------------------------------------------------------------------
DEFAULT_INT_COLS = ['số lõi', 'khe RAM', 'khe M.2', 'bộ nhớ', 'RAM tối đa', 'tdp']
DEFAULT_FLOAT_COLS = ['giá', 'xung cơ bản', 'xung boost', 'chiều dài']

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
    'bộ nhớ':       ['bộ nhớ', 'memory'],
    'socket':       ['socket', 'socket type', 'loại socket'],
}
