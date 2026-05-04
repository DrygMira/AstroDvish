from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.request_models import ChartRequest
from app.services.ephemeris_service import EphemerisService


def main() -> None:
    # Reference case from Ekaterina:
    # 1978-03-19 22:59:45 local at UTC+05 => 1978-03-19 17:59:45Z
    latitude = 40.23417
    longitude = 69.69481
    datetime_local = "1978-03-19T22:59:45"
    timezone_offset = "+05:00"
    datetime_utc = "1978-03-19T17:59:45Z"

    service = EphemerisService(ephe_path="ephe")
    payload = ChartRequest(
        datetime_utc=datetime_utc,
        latitude=latitude,
        longitude=longitude,
        house_system="P",
        zodiac_mode="tropical",
        sidereal_mode=None,
        aspect_orb_profile="avestan",
    )
    chart = service.calculate_chart(payload)

    debug_payload = {
        "input": {
            "datetime_local": datetime_local,
            "timezone_name": None,
            "timezone_offset": timezone_offset,
            "timezone_source": "manual_offset",
            "datetime_utc": datetime_utc,
            "latitude": latitude,
            "longitude": longitude,
            "house_system": "P",
            "zodiac_mode": "tropical",
        },
        "normalized": {
            "julian_day_ut": chart.normalized.julian_day_ut,
        },
        "angles": chart.angles,
        "houses_cusps": chart.houses.cusps,
        "houses_cusp_details": chart.houses.cusp_details,
        "objects": chart.objects,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    print(json.dumps(debug_payload, ensure_ascii=True, indent=2, default=lambda x: x.model_dump()))


if __name__ == "__main__":
    main()
