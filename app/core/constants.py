from __future__ import annotations

from typing import Final

SUPPORTED_HOUSE_SYSTEMS: Final[dict[str, str]] = {
    "P": "Placidus",
    "K": "Koch",
    "O": "Porphyry",
}

ZODIAC_SIGN_NAMES_EN: Final[tuple[str, ...]] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

ZODIAC_SIGN_NAMES_RU: Final[tuple[str, ...]] = (
    "Овен",
    "Телец",
    "Близнецы",
    "Рак",
    "Лев",
    "Дева",
    "Весы",
    "Скорпион",
    "Стрелец",
    "Козерог",
    "Водолей",
    "Рыбы",
)

ASCMC_LABELS: Final[dict[int, str]] = {
    0: "asc",
    1: "mc",
    2: "armc",
    3: "vertex",
    4: "equatorial_ascendant",
    5: "co_ascendant_koch",
    6: "co_ascendant_munkasey",
    7: "polar_ascendant",
}
