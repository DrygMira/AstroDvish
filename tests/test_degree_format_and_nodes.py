from __future__ import annotations

from app.services.zodiac_service import degree_to_dms


def test_degree_to_dms_formats_cleanly() -> None:
    assert degree_to_dms(28.736) == "28°44′10″"
    assert degree_to_dms(0.0) == "0°00′00″"


def test_true_south_node_math() -> None:
    true_node = 232.596161
    true_south_node = (true_node + 180.0) % 360.0
    assert abs(true_south_node - 52.596161) < 1e-6
