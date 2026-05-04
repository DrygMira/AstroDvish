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
    normalized = degree % 30.0
    whole_degrees = int(normalized)
    minutes_full = (normalized - whole_degrees) * 60
    whole_minutes = int(minutes_full)
    seconds = round((minutes_full - whole_minutes) * 60)

    if seconds == 60:
        seconds = 0
        whole_minutes += 1
    if whole_minutes == 60:
        whole_minutes = 0
        whole_degrees += 1

    return f"{whole_degrees}°{whole_minutes:02d}′{seconds:02d}″"
