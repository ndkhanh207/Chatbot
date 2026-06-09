"""Unit conversion calculator tool for the chatbot.

Provides exact numeric conversions so the AI never has to do math.
Call convert_unit(value, from_unit, to_unit) to get the exact result.
"""

# Conversion factors to base units
CONVERSIONS = {
    # Data storage (base: byte)
    'B': 1,
    'KB': 1024,
    'MB': 1024 ** 2,
    'GB': 1024 ** 3,
    'TB': 1024 ** 4,
    # Frequency (base: Hz)
    'HZ': 1,
    'KHZ': 1000,
    'MHZ': 1000 ** 2,
    'GHZ': 1000 ** 3,
    # Power (base: W)
    'W': 1,
    'KW': 1000,
    # Length (base: mm)
    'MM': 1,
    'CM': 10,
    'M': 1000,
}

# Friendly aliases
ALIASES = {
    'byte': 'B', 'bytes': 'B',
    'kilobyte': 'KB', 'kilobytes': 'KB',
    'megabyte': 'MB', 'megabytes': 'MB',
    'gigabyte': 'GB', 'gigabytes': 'GB',
    'terabyte': 'TB', 'terabytes': 'TB',
    'hertz': 'HZ',
    'kilohertz': 'KHZ',
    'megahertz': 'MHZ',
    'gigahertz': 'GHZ',
    'watt': 'W', 'watts': 'W',
    'kilowatt': 'KW', 'kilowatts': 'KW',
    'millimeter': 'MM', 'millimeters': 'MM',
    'centimeter': 'CM', 'centimeters': 'CM',
    'meter': 'M', 'meters': 'M',
    'vram': 'GB', 'VRAM': 'GB',
}


def _normalize_unit(unit_str: str) -> str:
    """Normalize a unit string to its canonical uppercase form."""
    u = unit_str.strip().upper()
    # Check direct match
    if u in CONVERSIONS:
        return u
    # Check lowercase alias
    lower = unit_str.strip().lower()
    if lower in ALIASES:
        return ALIASES[lower]
    raise ValueError(f"Unknown unit: '{unit_str}'. Supported: {list(CONVERSIONS.keys())}")


def convert_unit(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert a value from one unit to another.

    Parameters
    ----------
    value : float
        The numeric value to convert.
    from_unit : str
        The source unit (e.g., 'GB', 'MHz', 'W').
    to_unit : str
        The target unit (e.g., 'MB', 'GHz', 'W').

    Returns
    -------
    dict
        {
            "input_value": 64,
            "input_unit": "GB",
            "output_value": 65536,
            "output_unit": "MB",
            "formatted": "64 GB = 65536 MB"
        }

    Examples
    --------
    >>> convert_unit(64, 'GB', 'MB')
    {'input_value': 64, 'input_unit': 'GB', 'output_value': 65536, 'output_unit': 'MB', 'formatted': '64 GB = 65536 MB'}

    >>> convert_unit(3.5, 'GHz', 'MHz')
    {'input_value': 3.5, 'input_unit': 'GHz', 'output_value': 3500.0, 'output_unit': 'MHz', 'formatted': '3.5 GHz = 3500.0 MHz'}
    """
    from_canonical = _normalize_unit(from_unit)
    to_canonical = _normalize_unit(to_unit)

    # Convert to base unit, then to target
    base_value = value * CONVERSIONS[from_canonical]
    result = base_value / CONVERSIONS[to_canonical]

    # Format nicely — use int if it's a whole number
    if result == int(result):
        result = int(result)

    return {
        "input_value": value,
        "input_unit": from_canonical,
        "output_value": result,
        "output_unit": to_canonical,
        "formatted": f"{value} {from_canonical} = {result} {to_canonical}",
    }


def auto_convert_context_value(value: float, unit: str) -> list:
    """Given a value and its unit, return a list of useful conversions.

    This is used during context building to pre-compute common conversions
    so the AI sees exact numbers without needing to calculate.

    Parameters
    ----------
    value : float
        The numeric value.
    unit : str
        The current unit of the value.

    Returns
    -------
    list of str
        Formatted conversion strings, e.g. ["64 GB = 65536 MB"]

    Examples
    --------
    >>> auto_convert_context_value(64, 'GB')
    ['64 GB = 65536 MB', '64 GB = 67108864 KB']

    >>> auto_convert_context_value(3500, 'MHz')
    ['3500 MHz = 3.5 GHz']
    """
    unit_upper = unit.strip().upper()
    results = []

    # Define useful target units for each category
    USEFUL_TARGETS = {
        'GB': ['MB', 'KB', 'TB'],
        'MB': ['GB', 'KB'],
        'KB': ['MB', 'GB'],
        'TB': ['GB', 'MB'],
        'GHZ': ['MHZ'],
        'MHZ': ['GHZ'],
        'W': [],
        'MM': ['CM'],
        'CM': ['MM'],
    }

    targets = USEFUL_TARGETS.get(unit_upper, [])
    for target in targets:
        try:
            conv = convert_unit(value, unit_upper, target)
            results.append(conv['formatted'])
        except ValueError:
            pass

    return results


def convert_if_needed(value: float, unit: str, requested_unit: str | None = None) -> list:
    """Return conversions only when the requested unit differs from the default.

    Parameters
    ----------
    value : float
        The numeric value.
    unit : str
        The unit of the value as stored in the dataset (e.g., ``'GB'``).
    requested_unit : str | None, optional
        The unit the user explicitly asked for. If ``None`` or equal to
        ``unit`` the function returns an empty list.

    Returns
    -------
    list[str]
        A list of formatted conversion strings, e.g. ``['64 GB = 65536 MB']``.
    """
    if not requested_unit:
        return []
    # Normalize both units for comparison
    try:
        unit_norm = _normalize_unit(unit)
        req_norm = _normalize_unit(requested_unit)
    except ValueError:
        # If either unit is unknown, fall back to no conversion
        return []
    if unit_norm == req_norm:
        return []
    # If the requested unit is different, perform a single conversion
    try:
        conv = convert_unit(value, unit_norm, req_norm)
        return [conv['formatted']]
    except Exception:
        return []


if __name__ == '__main__':
    # Quick test
    print(convert_unit(64, 'GB', 'MB'))
    print(convert_unit(3.5, 'GHz', 'MHz'))
    print(convert_unit(256, 'GB', 'TB'))
    print(auto_convert_context_value(64, 'GB'))
    print(auto_convert_context_value(3500, 'MHz'))
