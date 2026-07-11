from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_STAGE1_FINAL = "Финальный результат пока не получен."


@dataclass
class SmokeResult:
    timezone_ok: bool
    stage1_ok: bool
    stage2_ok: bool
    profession_ok: bool
    multi_card_ok: bool
    reset_ok: bool


def _wait(page, ms: int) -> None:
    page.wait_for_timeout(ms)


def _text(page, selector: str) -> str:
    return page.locator(selector).inner_text().strip()


def _answer_stage2_event(page, title: str, date_text: str, impact: str) -> None:
    page.fill("#reTitle", title)
    page.fill("#reDateText", date_text)
    page.select_option("#reImpactLevel", impact)
    page.click("#reAnswerBtn")
    _wait(page, 1800)


def run_manual_v2_smoke(base_url: str = "http://127.0.0.1:8014/") -> SmokeResult:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        try:
            page.goto(f"{base_url}?v=manual-v2-smoke", wait_until="domcontentloaded", timeout=60000)
            _wait(page, 1200)
            page.click("#techModeToggleBtn")
            page.click("#tabRectDialogBtn")

            page.fill("#rdCityQuery", "Warsaw")
            page.fill("#rdLatitude", "52.22977")
            page.fill("#rdLongitude", "21.01178")
            page.fill("#rdBirthDate", "1990-01-15")
            page.evaluate(
                """
() => {
  document.getElementById('timezoneName').value = 'Europe/Warsaw';
  document.getElementById('timezoneMode').value = 'auto';
  document.getElementById('rdBirthDate').dispatchEvent(new Event('change', {bubbles: true}));
}
"""
            )
            page.click("#rdStartBtn")
            _wait(page, 4500)

            for _ in range(30):
                status = _text(page, "#rdStatus")
                final_text = _text(page, "#rdFinalResult")
                if final_text and final_text != DEFAULT_STAGE1_FINAL and "Получен финальный результат" in status:
                    break
                button = page.locator("#rdOptionsWrap button").first
                if button.count() and button.is_visible() and button.is_enabled():
                    button.click()
                _wait(page, 1800)

            timezone_ok = page.locator("#timezoneOffset").input_value() == "+01:00"
            stage1_ok = "Основной кандидат:" in _text(page, "#rdFinalResult")

            page.click("#tabRectEventsBtn")
            page.click("#reStartBtn")
            _wait(page, 1200)

            _answer_stage2_event(page, "Рождение ребёнка", "2005-11-07", "5")
            _answer_stage2_event(page, "Брак", "2010-06-12", "5")
            for _ in range(20):
                meta = _text(page, "#reQuestionMeta")
                if "profession_change" in meta:
                    _answer_stage2_event(page, "Смена профессии", "2016-04-10", "4")
                    break
                page.click("#reSkipBtn")
                _wait(page, 1200)
            page.click("#reFinalizeBtn")
            _wait(page, 2200)
            stage2_ok = "Событий: 3." in _text(page, "#reSummary")

            page.check("#rpUseAllRelevantV2Cards")
            page.click("#rpRunBtn")
            for _ in range(25):
                _wait(page, 2000)
                if _text(page, "#rpFormulaMultiCard") or "Ошибка" in _text(page, "#rpStatus"):
                    break
            multi_text = _text(page, "#rpFormulaMultiCard")
            multi_card_ok = (
                "selected_card_ids=RECT_CHILD_BIRTH_002_DRAFT, RECT_MARRIAGE_UNION_002_DRAFT, RECT_PROFESSION_CHANGE_002_DRAFT"
                in multi_text
                and "Per-card contribution" in multi_text
                and "Overall best candidate" in multi_text
                and "Overall working ranges" in multi_text
            )

            page.uncheck("#rpUseAllRelevantV2Cards")
            page.select_option("#rpFormulaCardId", "RECT_PROFESSION_CHANGE_002_DRAFT")
            page.click("#rpRunBtn")
            for _ in range(15):
                _wait(page, 2000)
                if _text(page, "#rpMethodsSummary") or "Ошибка" in _text(page, "#rpStatus"):
                    break
            methods_text = _text(page, "#rpMethodsSummary")
            profession_ok = (
                "RECT_PROFESSION_CHANGE_002_DRAFT" in methods_text
                and "Formula | Rule | Priority | Formula role | Status" in methods_text
            )

            page.click("#reResetBtn")
            _wait(page, 800)
            reset_ok = (
                _text(page, "#reSummary") == "Сбор событий ещё не завершён."
                and _text(page, "#rpFormulaMultiCard") == ""
                and page.locator("#rpUseAllRelevantV2Cards").is_checked() is False
            )

            return SmokeResult(
                timezone_ok=timezone_ok,
                stage1_ok=stage1_ok,
                stage2_ok=stage2_ok,
                profession_ok=profession_ok,
                multi_card_ok=multi_card_ok,
                reset_ok=reset_ok,
            )
        finally:
            browser.close()


def main() -> int:
    try:
        result = run_manual_v2_smoke()
    except PlaywrightTimeoutError as exc:
        print(f"SMOKE_TIMEOUT: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE_ERROR: {exc}")
        return 1

    print(result)
    return 0 if all(result.__dict__.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
