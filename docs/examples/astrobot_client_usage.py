from __future__ import annotations

from app.clients.astrobot_client import AstroDvishClient, get_chart_for_bot
from app.models.request_models import ChartRequest


def example_bot_flow() -> None:
    # 1) Bot receives birth data from Telegram user.
    chart_request = ChartRequest(
        datetime_utc="1984-11-13T11:35:00Z",
        latitude=53.9006,
        longitude=27.5590,
        house_system="P",
        zodiac_mode="tropical",
        sidereal_mode=None,
    )

    # 2) Bot calls AstroDvish through the adapter.
    with AstroDvishClient(base_url="http://127.0.0.1:8013", timeout_seconds=30) as client:
        chart_result = get_chart_for_bot(
            client,
            chart_request,
            request_id="tg-chat-12345-msg-67890",
        )

    # 3) Adapter returns structured computation JSON + request_id trace.
    calculation_json = chart_result.data.model_dump(mode="json")
    request_id = chart_result.request_id

    # 4) Bot passes calculation_json into GPT layer as immutable facts.
    # IMPORTANT:
    # - GPT may explain these facts in plain language.
    # - GPT must NOT invent degrees, houses, aspects, or orbs.
    # - Any precise astro numbers must come only from calculation_json.
    _ = request_id
    _ = calculation_json


if __name__ == "__main__":
    example_bot_flow()

