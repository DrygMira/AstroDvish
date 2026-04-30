from __future__ import annotations

import pytest

from app.core.errors import TimezoneLookupError
from app.utils import timezone_lookup


class _TimezoneFinderNone:
    def timezone_at(self, *, lng: float, lat: float):
        return None


class _TimezoneFinderInvalid:
    def timezone_at(self, *, lng: float, lat: float):
        return "Invalid/Timezone"


def test_timezone_lookup_none_returns_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timezone_lookup, "_timezone_finder", _TimezoneFinderNone())

    with pytest.raises(TimezoneLookupError) as exc_info:
        timezone_lookup.resolve_timezone_name(latitude=53.9, longitude=27.56667)

    assert exc_info.value.message == "Could not determine timezone for coordinates"


def test_timezone_lookup_invalid_name_returns_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timezone_lookup, "_timezone_finder", _TimezoneFinderInvalid())

    with pytest.raises(TimezoneLookupError) as exc_info:
        timezone_lookup.resolve_timezone_name(latitude=53.9, longitude=27.56667)

    assert exc_info.value.message == "Invalid timezone name returned for coordinates"
