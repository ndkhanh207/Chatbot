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

# Base directory for CSV data files. Can be overridden by env var PC_STORE_DATA_DIR.
DATA_DIR = Path(os.getenv('PC_STORE_DATA_DIR', Path(__file__).resolve().parent.parent / 'data'))


def resolve_data_path(filename: str) -> Path:
    """Return absolute path to a data file located in the project's data folder.

    Args:
        filename: Name of the CSV or other data file.
    Returns:
        Path object pointing to the file.
    """
    return DATA_DIR / filename
