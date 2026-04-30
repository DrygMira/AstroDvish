from __future__ import annotations

from app.core.constants import ZODIAC_SIGN_NAMES_EN


def normalize_degree(degree: float) -> float:
    return degree % 360.0


def resolve_sign(longitude_deg: float) -> tuple[int, str, float]:
    normalized = normalize_degree(longitude_deg)
    sign_index = int(normalized // 30)
    sign_degree = normalized % 30
    return sign_index, ZODIAC_SIGN_NAMES_EN[sign_index], sign_degree


def degree_to_dms(degree: float) -> str:
    whole_degrees = int(degree)
    minutes_full = (degree - whole_degrees) * 60
    whole_minutes = int(minutes_full)
    seconds = (minutes_full - whole_minutes) * 60
    return f'{whole_degrees}°{whole_minutes:02d}\'{seconds:05.2f}"'

