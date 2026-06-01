from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def get_main_ui_bundle(client: TestClient) -> tuple[object, str]:
    response = client.get("/")
    css_response = client.get("/static/css/styles.css")
    js_dir = Path(__file__).resolve().parents[1] / "web_ui" / "static" / "js"
    js_chunks: list[str] = []

    for js_path in sorted(js_dir.glob("*.js")):
        js_response = client.get(f"/static/js/{js_path.name}")
        js_chunks.append(js_response.text)

    bundle_text = "\n".join(
        [
            response.text,
            css_response.text,
            *js_chunks,
        ]
    )
    return response, bundle_text
