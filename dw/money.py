"""Local currency for a plan: which currency a city uses, how to show it, and how to turn the
US-style price guesses into local ones.

Two kinds of number live here, and both are rough on purpose:

* A currency's factor is how many local units buy what one US dollar buys on a cheap night
  out in that currency's home market. It mixes the exchange rate with local bar prices, so it
  is not an exchange rate. Google's "pricey" thresholds are scaled by it.
* A country's scale does the same for one country, where it differs from the currency's
  default (a beer in Lisbon costs less than one in Dublin, both in euros). The type-based
  guesses in places.estimate_price are US prices, and get multiplied by this.

A city whose country is not listed falls back to US dollars.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

# code: (prefix, suffix, factor)
CURRENCIES: dict[str, tuple[str, str, float]] = {
    "USD": ("$", "", 1.0),
    "EUR": ("€", "", 0.8),
    "GBP": ("£", "", 0.75),
    "CAD": ("CA$", "", 1.2),
    "AUD": ("A$", "", 1.4),
    "NZD": ("NZ$", "", 1.5),
    "MXN": ("MX$", "", 9.0),
    "CHF": ("CHF ", "", 1.0),
    "SEK": ("", " kr", 9.0),
    "NOK": ("", " kr", 12.0),
    "DKK": ("", " kr", 6.5),
    "ISK": ("", " kr", 140.0),
    "PLN": ("", " zł", 2.2),
    "CZK": ("", " Kč", 14.0),
    "HUF": ("", " Ft", 220.0),
    "RON": ("", " lei", 2.3),
    "JPY": ("¥", "", 90.0),
    "KRW": ("₩", "", 900.0),
    "CNY": ("CN¥", "", 4.0),
    "HKD": ("HK$", "", 7.0),
    "SGD": ("S$", "", 1.3),
    "THB": ("฿", "", 15.0),
    "VND": ("", "₫", 3500.0),
    "IDR": ("Rp ", "", 5000.0),
    "PHP": ("₱", "", 25.0),
    "MYR": ("RM ", "", 3.0),
    "INR": ("₹", "", 40.0),
    "BRL": ("R$", "", 2.5),
    "CLP": ("CLP$", "", 600.0),
    "COP": ("COL$", "", 2500.0),
    "PEN": ("S/ ", "", 2.5),
    "ZAR": ("R", "", 8.0),
    "ILS": ("₪", "", 3.0),
    "AED": ("AED ", "", 3.5),
}

# country: (currency, scale or None to use the currency's factor)
COUNTRIES: dict[str, tuple[str, float | None]] = {
    "US": ("USD", None), "PR": ("USD", None),
    "CA": ("CAD", None), "MX": ("MXN", None), "GB": ("GBP", None),
    "IE": ("EUR", 1.0), "PT": ("EUR", 0.55), "ES": ("EUR", 0.65), "FR": ("EUR", 0.95), "DE": ("EUR", 0.8),
    "IT": ("EUR", 0.75), "NL": ("EUR", 0.9), "BE": ("EUR", 0.9), "AT": ("EUR", 0.85), "GR": ("EUR", 0.65),
    "FI": ("EUR", 1.0), "EE": ("EUR", 0.7), "LV": ("EUR", 0.6), "LT": ("EUR", 0.6), "SK": ("EUR", 0.6),
    "SI": ("EUR", 0.65), "HR": ("EUR", 0.65), "CY": ("EUR", 0.75), "MT": ("EUR", 0.7), "LU": ("EUR", 1.0),
    "CH": ("CHF", None), "SE": ("SEK", None), "NO": ("NOK", None), "DK": ("DKK", None), "IS": ("ISK", None),
    "PL": ("PLN", None), "CZ": ("CZK", None), "HU": ("HUF", None), "RO": ("RON", None),
    "JP": ("JPY", None), "KR": ("KRW", None), "CN": ("CNY", None), "HK": ("HKD", None), "SG": ("SGD", None),
    "TH": ("THB", None), "VN": ("VND", None), "ID": ("IDR", None), "PH": ("PHP", None), "MY": ("MYR", None),
    "IN": ("INR", None), "BR": ("BRL", None), "CL": ("CLP", None), "CO": ("COP", None), "PE": ("PEN", None),
    "ZA": ("ZAR", None), "IL": ("ILS", None), "AE": ("AED", None), "AU": ("AUD", None), "NZ": ("NZD", None),
}


def known(code: str | None) -> bool:
    return code in CURRENCIES


def currency_for(country: str | None) -> str:
    return COUNTRIES.get((country or "").upper(), ("USD", None))[0]


def factor(code: str | None) -> float:
    return CURRENCIES.get(code or "USD", CURRENCIES["USD"])[2]


def country_scale(country: str | None) -> float:
    """Multiply a US price guess by this to get a local one, in the country's currency."""
    cur, scale = COUNTRIES.get((country or "").upper(), ("USD", None))
    return scale if scale is not None else factor(cur)


def step(code: str | None) -> int:
    """Prices round to this. One unit for dollars and euros, tens for yen, hundreds for won."""
    f = factor(code)
    return 1 if f < 10 else 10 ** int(math.floor(math.log10(f)))


def nice(amount: float, code: str | None) -> int:
    s = step(code)
    return int(round(amount / s) * s)


def fmt(amount: float, code: str | None) -> str:
    prefix, suffix, _ = CURRENCIES.get(code or "USD", CURRENCIES["USD"])
    return f"{prefix}{int(round(amount)):,}{suffix}"


def _nice_step(x: float) -> int:
    """Round a slider step to 1, 2 or 5 times a power of ten."""
    if x <= 1:
        return 1
    p = 10 ** int(math.floor(math.log10(x)))
    return min((m * p for m in (1, 2, 5, 10)), key=lambda v: abs(v - x))


def budget_ui(code: str) -> dict[str, Any]:
    """Slider range and quick picks for the budget, matching the US $20 to $150 slider."""
    f = factor(code)
    st = _nice_step(5 * f)
    r = lambda usd: max(st, int(round(usd * f / st) * st))  # noqa: E731
    chips = list(dict.fromkeys(r(v) for v in (30, 50, 75, 100)))
    return {"min": r(20), "max": r(150), "step": st, "default": r(50), "chips": chips}


def budget_limits(code: str) -> tuple[float, float]:
    """What the server accepts for a per-person budget, in the plan's currency."""
    f = factor(code)
    return 5 * f, 300 * f


def client_table() -> dict[str, Any]:
    """Everything the page needs to show money before a plan exists."""
    return {
        "countries": {cc: cur for cc, (cur, _) in COUNTRIES.items()},
        "currencies": {
            code: {"prefix": pre, "suffix": suf, "factor": f, "step": step(code), "budget": budget_ui(code)}
            for code, (pre, suf, f) in CURRENCIES.items()
        },
    }


def guess_currency(places: list[dict[str, Any]]) -> str | None:
    """The currency most of Google's price ranges use, when the country is not known."""
    seen = Counter(p["price"].get("currency") for p in places if not p["price"].get("guess"))
    seen.pop(None, None)
    top = [c for c, _ in seen.most_common(1) if known(c)]
    return top[0] if top else None


def localize_price(price: dict[str, Any], code: str, country: str | None) -> dict[str, Any]:
    """A copy of one price dict, in the plan's currency. Tier is left alone: it was judged in the
    price's own currency, so it still holds."""
    src = price.get("currency") or "USD"
    if src == code:
        return dict(price)
    if price.get("guess"):
        mult = country_scale(country) if currency_for(country) == code else factor(code)
    else:
        mult = factor(code) / factor(src)
    out = dict(price)
    low, high = nice(price["low"] * mult, code), nice(price["high"] * mult, code)
    mid = nice(price["mid"] * mult, code)
    s = step(code)
    low = max(s, low)
    high = max(low, high)
    out.update(low=low, high=high, mid=min(max(mid, low), high), currency=code)
    if not price.get("guess"):
        out["basis"] = f"Google says people usually spend {fmt(price['low'], src)} to {fmt(price['high'], src)}, about {fmt(low, code)} to {fmt(high, code)}"
    return out


def localize(places: list[dict[str, Any]], code: str, country: str | None) -> list[dict[str, Any]]:
    """Copies of the places with every price in one currency. The input is never changed, since
    callers may keep it in a cache."""
    return [{**p, "price": localize_price(p["price"], code, country)} for p in places]
