#!/usr/bin/env python3
"""Инструмент формула-карточек ректификации (V2 draft, explicit-only).

Режимы:
  python scripts/card_tool.py add --source <txt> --card-id ID --event-type TYPE
      --meta <meta.json> --expected-total N
      Разобрать txt-пак формул Екатерины, собрать draft-карточку, записать JSON.
      Если card_id уже существует — показывает diff перед перезаписью.

  python scripts/card_tool.py verify <card_id> [--live]
      Локальные проверки (структура, status=draft, счётчики). С --live — ещё и
      реальный прогон через API (по умолчанию http://127.0.0.1:8014 или :8016).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.cardlib import card_io, parser as card_parser, verify as card_verify

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CARDS_ROOT = REPO_ROOT / "product" / "astrobot_content_pack" / "formula_cards" / "rectification"

# Опорная тестовая карта рождения — тот же фикстур, что используется во всех
# live-проверках этой сессии (live_check.py / live_default_check.py).
REFERENCE_BIRTH_PAYLOAD = {
    "birth_date_local": "1985-05-12",
    "latitude": 53.9006,
    "longitude": 27.5590,
    "timezone_name": "Europe/Minsk",
    "asc_windows": [
        {"start_local": "1985-05-12T14:00:00", "end_local": "1985-05-12T14:20:00", "sign_name_en": "Libra"}
    ],
}


def cmd_add(args: argparse.Namespace) -> int:
    cards_root = Path(args.cards_root)
    source_path = Path(args.source)
    meta_path = Path(args.meta)

    text = source_path.read_text(encoding="utf-8")
    meta = card_io.load_meta(meta_path)
    parsed = card_parser.parse_formulas(text, meaning=meta.source_meaning, comment=meta.source_comment, source_name=source_path.name)
    new_card = card_io.build_card(
        card_id=args.card_id,
        event_type=args.event_type,
        meta=meta,
        parsed=parsed,
        source_files=[str(source_path)],
        expected_total=args.expected_total,
    )

    old_card = card_io.read_card(args.card_id, cards_root)
    diff = card_io.diff_cards(old_card, new_card)

    print(f"[add] {args.card_id} -> {args.event_type}")
    print(f"[add] разобрано формул: {parsed.imported_formula_count} (ожидалось {args.expected_total})")
    print(f"[add] тиры: {parsed.tier_counts}")
    if parsed.malformed_blocks:
        print(f"[add] ПРОБЛЕМА: {len(parsed.malformed_blocks)} блок(ов) не распознано:")
        for block in parsed.malformed_blocks:
            print(f"       block #{block['block_index']}: {block['preview']}")
    if parsed.conflicts_for_review:
        print(f"[add] {len(parsed.conflicts_for_review)} конфликт(ов) тиров -> оставлен более сильный, флагнуто на ревью")

    if old_card is not None:
        print(f"[add] {args.card_id} уже существует — diff с текущей версией:")
        if diff.is_empty:
            print("       без изменений в правилах")
        else:
            if diff.added_rule_ids:
                print(f"       + добавлено: {diff.added_rule_ids}")
            if diff.removed_rule_ids:
                print(f"       - убрано: {diff.removed_rule_ids}")
            if diff.tier_changed:
                for item in diff.tier_changed:
                    print(f"       ~ {item['rule_id']}: {item['old_tier']} -> {item['new_tier']}")
        if not args.yes:
            if input("Перезаписать? [y/N] ").strip().lower() not in ("y", "yes"):
                print("[add] отменено.")
                return 1

    path = card_io.write_card(new_card, cards_root)
    print(f"[add] записано: {path}")

    result = card_verify.verify_card(args.card_id, cards_root)
    print(f"[add] verify: {'OK' if result.ok else 'ЕСТЬ ЗАМЕЧАНИЯ'}")
    for problem in result.problems:
        print(f"       - {problem}")
    return 0 if result.ok else 1


def cmd_verify(args: argparse.Namespace) -> int:
    cards_root = Path(args.cards_root)
    result = card_verify.verify_card(args.card_id, cards_root)
    print(f"[verify] {args.card_id}: {'OK' if result.ok else 'ЕСТЬ ЗАМЕЧАНИЯ'}")
    for check, passed in result.checks.items():
        print(f"         {'OK  ' if passed else 'FAIL'} {check}")
    for problem in result.problems:
        print(f"         - {problem}")

    if not args.live:
        return 0 if result.ok else 1

    if not result.checks.get("loads"):
        print("[verify --live] пропущено: карточка не грузится локально")
        return 1

    loader_card = card_io.read_card(args.card_id, cards_root) or {}
    event_type = loader_card.get("event_type", "")
    live_ok, live_message = _live_check(
        card_id=args.card_id,
        event_type=event_type,
        host_url=args.host_url,
        api_base_url=args.api_base_url,
    )
    print(f"[verify --live] {'OK' if live_ok else 'FAIL'}: {live_message}")
    return 0 if (result.ok and live_ok) else 1


def _http_post_json(url: str, body: dict, timeout: int = 120) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _find_key(obj: object, key: str) -> object | None:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def _live_check(*, card_id: str, event_type: str, host_url: str, api_base_url: str) -> tuple[bool, str]:
    event = {
        "event_id": "card_tool_check",
        "event_type": event_type,
        "title": f"card_tool verify {card_id}",
        "date_text": "2012-06-15",
        "date_precision": "exact",
        "start_date": "2012-06-15",
        "end_date": "2012-06-15",
        "impact_level": 5,
        "reversibility": "irreversible",
        "life_area": "family",
        "sequence_number": 1,
        "notes": "",
        "user_skipped": False,
    }
    body = {
        "api_base_url": api_base_url,
        "payload": {
            **REFERENCE_BIRTH_PAYLOAD,
            "events": [event],
            "settings": {"formula_card_ids": [card_id]},
        },
    }
    try:
        status, data = _http_post_json(f"{host_url}/api/rectification/pro/run", body, timeout=120)
    except (urllib.error.URLError, OSError) as exc:
        return False, f"не удалось подключиться к {host_url}: {exc}"

    if status != 200:
        return False, f"HTTP {status}: {json.dumps(data, ensure_ascii=False)[:400]}"

    found_card_id = _find_key(data, "card_id")
    if found_card_id != card_id:
        return False, f"карточка не применилась: card_id в ответе = {found_card_id!r}, ожидался {card_id!r}"
    return True, f"карточка применилась, card_id={found_card_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Инструмент формула-карточек ректификации")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="разобрать txt и записать/обновить draft-карточку")
    p_add.add_argument("--source", required=True, help="путь к txt-паку формул Екатерины")
    p_add.add_argument("--card-id", required=True)
    p_add.add_argument("--event-type", required=True)
    p_add.add_argument("--meta", required=True, help="путь к meta.json (title/houses/planets/...)")
    p_add.add_argument("--expected-total", type=int, required=True, help="ожидаемое число формул из шапки пака")
    p_add.add_argument("--cards-root", default=str(DEFAULT_CARDS_ROOT))
    p_add.add_argument("-y", "--yes", action="store_true", help="перезаписать без подтверждения")

    p_verify = sub.add_parser("verify", help="проверить карточку (локально, опционально live)")
    p_verify.add_argument("card_id")
    p_verify.add_argument("--cards-root", default=str(DEFAULT_CARDS_ROOT))
    p_verify.add_argument("--live", action="store_true", help="дополнительно прогнать через API")
    p_verify.add_argument("--host-url", default="http://127.0.0.1:8014", help="куда слать запрос (web_ui)")
    p_verify.add_argument("--api-base-url", default="", help="api_base_url для web_ui (пусто = серверный дефолт)")

    args = parser.parse_args()
    if args.command == "add":
        return cmd_add(args)
    return cmd_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
