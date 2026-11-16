"""Number formats used everywhere in the app (spec 017).

- a true minus sign (U+2212) instead of the hyphen;
- thousands separators; compact money with the currency symbol ("€197k", "$1.2m");
- units after the number with a thin space ("1,250 EUR/t" stays readable);
- percent with one decimal below 10 %, none above; ranges with an en dash.
"""

import math

MINUS = "−"
THIN = " "
SYMBOLS = {"EUR": "€", "USD": "$"}
NA = "n/a"


def _missing(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _minus(text: str) -> str:
    return text.replace("-", MINUS)


def number(value: float | None, decimals: int = 0, signed: bool = False) -> str:
    """1,234 / −1,234 / +1,234 (signed)."""
    if _missing(value):
        return NA
    assert value is not None
    sign = "+" if signed else ""
    return _minus(f"{value:{sign},.{decimals}f}")


def pct(value: float | None, signed: bool = True) -> str:
    """'+3.3 %', '−12 %': one decimal below 10 %, none from 10 % on."""
    if _missing(value):
        return NA
    assert value is not None
    decimals = 1 if abs(value) < 10 else 0
    return number(value, decimals, signed) + f"{THIN}%"


def money(value: float | None, currency: str = "EUR", signed: bool = False) -> str:
    """Compact money: '€197k', '−€197k', '$1.2m', '€850'."""
    if _missing(value):
        return NA
    assert value is not None
    symbol = SYMBOLS.get(currency, currency + " ")
    size = abs(value)
    if size >= 1e6:
        body = f"{size / 1e6:,.1f}m"
    elif size >= 1e3:
        body = f"{size / 1e3:,.0f}k"
    else:
        body = f"{size:,.0f}"
    sign = MINUS if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}{symbol}{body}"


def per_tonne(value: float | None, currency: str = "EUR", signed: bool = False) -> str:
    """'1,250 EUR/t'."""
    if _missing(value):
        return NA
    return f"{number(value, 0, signed)}{THIN}{currency}/t"


def span(low: float | None, high: float | None, decimals: int = 0, signed: bool = False) -> str:
    """'1,050–1,230' (en dash); one number when both ends round the same."""
    if _missing(low) or _missing(high):
        return NA
    assert low is not None and high is not None
    a, b = number(low, decimals, signed), number(high, decimals, signed)
    return a if a == b else f"{a}–{b}"


def pct_span(low: float | None, high: float | None) -> str:
    """'16–39 %' or '40 %'."""
    if _missing(low) or _missing(high):
        return NA
    assert low is not None and high is not None
    a, b = f"{low:.0f}", f"{high:.0f}"
    return f"{b}{THIN}%" if a == b else f"{a}–{b}{THIN}%"
