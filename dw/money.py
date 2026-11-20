"""Local currency for prices, budgets and exports.

The planner works in one internal unit (US dollars of a typical US night out). Money is converted
at the edges: the budget a visitor types in local money comes in through `to_internal`, and every
price shown leaves through `fmt`.

`level` is NOT an exchange rate. It is roughly how many units of local money buy what one US
dollar buys on a cheap night out there (a pint, a taco, a slice). A beer in Lisbon costs fewer
euros than it costs dollars in Austin, so Lisbon's level is below the euro's exchange rate.
These are rough, hand-set numbers, and every price in the app is labeled an estimate.
When Google lists a real local spend range for a place, that range is used instead.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Currency:
    code: str
    symbol: str
    level: float  # local units per internal unit (see module notes)
    suffix: bool = False  # "80 kr" rather than "kr80"

    def as_dict(self) -> dict:
        return asdict(self)


def _c(code, symbol, level, suffix=False):
    return Currency(code, symbol, level, suffix)


USD = _c("USD", "$", 1.0)

# country code -> currency and rough price level for a cheap night out
BY_COUNTRY: dict[str, Currency] = {
    "US": USD, "PR": USD,
    "CA": _c("CAD", "$", 1.3), "MX": _c("MXN", "$", 12), "AU": _c("AUD", "$", 1.4), "NZ": _c("NZD", "$", 1.5),
    "GB": _c("GBP", "£", 0.75), "IE": _c("EUR", "€", 0.9),
    "FR": _c("EUR", "€", 0.85), "DE": _c("EUR", "€", 0.75), "NL": _c("EUR", "€", 0.85), "BE": _c("EUR", "€", 0.85),
    "LU": _c("EUR", "€", 0.9), "AT": _c("EUR", "€", 0.8), "IT": _c("EUR", "€", 0.75), "ES": _c("EUR", "€", 0.65),
    "PT": _c("EUR", "€", 0.55), "GR": _c("EUR", "€", 0.6), "FI": _c("EUR", "€", 0.95), "EE": _c("EUR", "€", 0.65),
    "LV": _c("EUR", "€", 0.6), "LT": _c("EUR", "€", 0.6), "SK": _c("EUR", "€", 0.55), "SI": _c("EUR", "€", 0.6),
    "HR": _c("EUR", "€", 0.6), "MT": _c("EUR", "€", 0.7), "CY": _c("EUR", "€", 0.7),
    "CH": _c("CHF", "CHF ", 1.0), "DK": _c("DKK", "kr", 6.5, True), "SE": _c("SEK", "kr", 8, True),
    "NO": _c("NOK", "kr", 10, True), "IS": _c("ISK", "kr", 150, True), "CZ": _c("CZK", "Kč", 14, True),
    "PL": _c("PLN", "zł", 2.4, True), "HU": _c("HUF", "Ft", 220, True), "RO": _c("RON", "lei", 2.5, True),
    "TR": _c("TRY", "₺", 18), "JP": _c("JPY", "¥", 100), "KR": _c("KRW", "₩", 1100), "CN": _c("CNY", "¥", 4.5),
    "HK": _c("HKD", "HK$", 7), "TW": _c("TWD", "NT$", 25), "SG": _c("SGD", "S$", 1.3), "TH": _c("THB", "฿", 18),
    "VN": _c("VND", "₫", 12000, True), "MY": _c("MYR", "RM", 2.5), "PH": _c("PHP", "₱", 30), "IN": _c("INR", "₹", 30),
    "AE": _c("AED", "AED ", 3.7), "IL": _c("ILS", "₪", 3.5), "ZA": _c("ZAR", "R", 9), "BR": _c("BRL", "R$", 3),
    "CO": _c("COP", "$", 2500), "CL": _c("CLP", "$", 600), "PE": _c("PEN", "S/", 2.5),
}
BY_CODE: dict[str, Currency] = {}
for _cur in BY_COUNTRY.values():
    BY_CODE.setdefault(_cur.code, _cur)
BY_CODE["EUR"] = _c("EUR", "€", 0.75)  # a middle euro level when only the currency is known


def for_country(country: str | None) -> Currency | None:
    """None when the country is unknown, so the caller can fall back to what the data shows."""
    return BY_COUNTRY.get((country or "").upper())


def for_code(code: str | None) -> Currency | None:
    return BY_CODE.get((code or "").upper())


def from_dict(d: dict | None) -> Currency:
    """Rebuild from a posted plan. Only known currencies are accepted, never a made-up level."""
    if isinstance(d, dict):
        known = BY_CODE.get(str(d.get("code", "")).upper())
        if known:
            for c in BY_COUNTRY.values():
                if c.code == known.code and abs(c.level - float(d.get("level") or 0)) < 1e-9:
                    return c
            return known
    return USD


def step(cur: Currency) -> int:
    """Round shown amounts to what people actually say: $14, ¥1,400, ₫170,000."""
    lv = cur.level
    return 1 if lv < 8 else 10 if lv < 80 else 100 if lv < 800 else 1000


def local(amount: float, cur: Currency) -> int:
    s = step(cur)
    return int(round(amount * cur.level / s) * s)


def to_internal(local_amount: float, cur: Currency) -> float:
    return local_amount / cur.level


def fmt(amount: float, cur: Currency) -> str:
    """Internal amount -> local money text."""
    n = f"{local(amount, cur):,}"
    return f"{n} {cur.symbol}" if cur.suffix else f"{cur.symbol}{n}"


def fmt_local(local_amount: float, cur: Currency) -> str:
    """Amount already in local money (like a typed budget) -> text."""
    n = f"{int(round(local_amount)):,}"
    return f"{n} {cur.symbol}" if cur.suffix else f"{cur.symbol}{n}"


def budget_choices(cur: Currency) -> dict:
    """Slider range and quick picks for the budget step, in round local numbers."""
    s = step(cur) * (5 if cur.level >= 8 else 1)
    def r(x):
        return int(max(s, round(x * cur.level / s) * s))
    return {"min": r(20), "max": r(150), "step": s if cur.level >= 8 else 5, "default": r(50), "chips": [r(30), r(50), r(75), r(100)]}
