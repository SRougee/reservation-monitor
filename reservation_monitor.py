"""
DOM Reservation Monitor
=======================

Fast, browser-realistic Playwright monitor.

The monitor assumes availability is NOT pushed automatically by the website.
It uses the normal visible "Reload Availability" control, waits for the
browser-visible grid update, then immediately checks for all available cells.

It does not access Cloudflare, D1, Worker code, Admin Log, or private server
interfaces. It only interacts with the logged-in reservation page.

The monitor runs continuously until Ctrl+C.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


# ============================================================
# SETTINGS
# ============================================================

URL = "https://reservation-monitor-test.ronaldjennings84.workers.dev/"
BLOCK_SELECTOR = ".booking-block"
TARGET_TEXT = ""
AVAILABLE_CLASS = "available"
RESERVE_BUTTON_SELECTOR = "#reserveButton"
REFRESH_BUTTON_SELECTOR = "#reloadGrid"
RESERVATION_MESSAGE_SELECTOR = "#message"
RESERVATION_SUCCESS_TEXT = "Reserved cells:"
PAGE_LOAD_TIMEOUT = 10_000
DEBUG = True
PROFILE_DIR = Path(".browser-profile")


# ============================================================
# LOGGING
# ============================================================


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(message: str) -> None:
    print(f"[{timestamp()}] {message}", flush=True)


# ============================================================
# BROWSER HELPERS
# ============================================================


def page_is_alive(page) -> bool:
    try:
        return not page.is_closed()
    except Exception:
        return False


def grid_signature(page) -> str:
    """Return a compact browser-side signature of cell state."""
    return page.locator(BLOCK_SELECTOR).evaluate_all(
        "elements => elements.map(e => `${e.dataset.cellId}:${e.className}`).join('|')"
    )


def wait_for_grid_update(page, previous_signature: str) -> bool:
    """Wait for the normal Reload button's DOM update; no fixed sleep."""
    try:
        page.wait_for_function(
            """
            previous => {
                const elements = [...document.querySelectorAll('.booking-block')];
                const current = elements.map(e => `${e.dataset.cellId}:${e.className}`).join('|');
                return current !== previous;
            }
            """,
            previous_signature,
            timeout=3_000,
        )
        return True
    except PlaywrightTimeoutError:
        return False


def find_available_blocks(page):
    """Find all currently available matching blocks with one browser query."""
    locator = page.locator(f"{BLOCK_SELECTOR}.{AVAILABLE_CLASS}")
    count = locator.count()
    result = []

    if TARGET_TEXT:
        target = TARGET_TEXT.casefold()
        for index in range(count):
            block = locator.nth(index)
            if target in (block.inner_text() or "").casefold():
                result.append(block)
    else:
        for index in range(count):
            result.append(locator.nth(index))

    return result


def select_all_available(page) -> list[int]:
    """Select all available matching cells in one browser-side operation."""
    selector = f"{BLOCK_SELECTOR}.{AVAILABLE_CLASS}"
    try:
        ids = page.locator(selector).evaluate_all(
            """
            (elements, targetText) => {
                const target = String(targetText || '').toLowerCase();
                const selected = [];

                for (const element of elements) {
                    if (target && !element.innerText.toLowerCase().includes(target)) continue;
                    if (!element.classList.contains('available')) continue;
                    element.click();
                    selected.push(Number(element.dataset.cellId));
                }
                return selected;
            }
            """,
            TARGET_TEXT,
        )
        return [int(value) for value in ids]
    except Exception as exc:
        log(f"Could not select all available cells in one operation: {exc}")
        return []


def clear_reservation_message(page) -> None:
    try:
        page.locator(RESERVATION_MESSAGE_SELECTOR).evaluate(
            "element => { element.textContent = ''; }"
        )
    except Exception:
        pass


def reserve_selected(page) -> bool:
    """Submit all selected cells and wait for the new browser-visible result."""
    try:
        button = page.locator(RESERVE_BUTTON_SELECTOR).first
        button.wait_for(state="visible", timeout=2_000)
        clear_reservation_message(page)

        log("Submitting all selected cells...")
        button.click()

        page.wait_for_function(
            "() => Boolean(document.querySelector('#message')?.textContent?.trim())",
            timeout=3_000,
        )

        text = page.locator(RESERVATION_MESSAGE_SELECTOR).inner_text(timeout=500).strip()
        if text.startswith(RESERVATION_SUCCESS_TEXT):
            log(f"Website confirmed reservation: {text}")
            return True

        log(f"Website reservation response: {text or 'no readable response'}")
        return False

    except PlaywrightTimeoutError:
        log("ERROR: No reservation response received within 3 seconds.")
        return False
    except Exception as exc:
        log(f"ERROR submitting reservation: {exc}")
        return False


def reload_and_process(page) -> None:
    """Press the site's normal refresh control and react immediately to its DOM result."""
    previous_signature = grid_signature(page)

    refresh = page.locator(REFRESH_BUTTON_SELECTOR).first
    refresh.wait_for(state="visible", timeout=2_000)

    start = time.perf_counter()
    refresh.click()
    log("Reload Availability clicked.")

    # The browser itself updates the grid. We wait for that visible change,
    # rather than sleeping for an arbitrary amount of time.
    changed = wait_for_grid_update(page, previous_signature)
    elapsed_ms = (time.perf_counter() - start) * 1000

    if changed:
        log(f"Grid changed after reload ({elapsed_ms:.1f} ms). Checking immediately.")
    else:
        log(f"No visible grid change after reload within 3 seconds ({elapsed_ms:.1f} ms).")


def process_available(page) -> bool:
    """Find and reserve every currently available matching cell."""
    blocks = find_available_blocks(page)
    if not blocks:
        return False

    ids_preview = []
    for block in blocks:
        try:
            ids_preview.append(int(block.get_attribute("data-cell-id")))
        except Exception:
            pass

    log(f"Found {len(blocks)} available matching cell(s): {ids_preview}")
    selected_ids = select_all_available(page)

    if not selected_ids:
        log("Available cells were found but none could be selected.")
        return False

    log(f"Selected ALL {len(selected_ids)} matching cell(s): {selected_ids}")
    return reserve_selected(page)


# ============================================================
# MAIN
# ============================================================


def validate_settings() -> None:
    if "YOUR-WEBSITE-HERE" in URL:
        print("ERROR: Change URL in the SETTINGS section.")
        sys.exit(1)


def main() -> None:
    validate_settings()

    print()
    print("=" * 70)
    print("                 DOM RESERVATION MONITOR")
    print("=" * 70)
    print(f"URL:                 {URL}")
    print(f"Block selector:      {BLOCK_SELECTOR}")
    print(f"Available class:     {AVAILABLE_CLASS}")
    print(f"Refresh selector:    {REFRESH_BUTTON_SELECTOR}")
    print(f"Reserve selector:    {RESERVE_BUTTON_SELECTOR}")
    print("Detection:           Browser-visible DOM change")
    print("Full page reloads:   DISABLED")
    print("Admin/log access:    DISABLED")
    print("Selection:           ALL matching cells in one browser operation")
    print("Refresh method:      Normal Reload Availability button")
    print("Runtime:             Continuous until Ctrl+C")
    print("=" * 70)
    print()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = None

        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1400, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(2_000)
            ready = False

            while True:
                if not page_is_alive(page):
                    log("Browser page is unavailable. Attempting recovery...")
                    page = context.new_page()
                    page.set_default_timeout(2_000)
                    ready = False

                try:
                    if page.url == "about:blank":
                        log("Opening website...")
                        page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                except Exception as exc:
                    log(f"Could not open/navigate page: {exc}")
                    time.sleep(1)
                    continue

                if not ready:
                    print()
                    print("=" * 70)
                    print("                         LOGIN / READY")
                    print("=" * 70)
                    print("Log in manually if needed and navigate to the Reservations page.")
                    print("Type Y or YES when ready to start monitoring.")
                    print("The monitor will press the normal Reload Availability button.")
                    print("It will not reload the whole page.")
                    print("=" * 70)
                    print()

                    while True:
                        try:
                            answer = input("Are you ready to start monitoring? [Y/N]: ").strip().casefold()
                        except EOFError:
                            answer = ""
                        if answer in {"y", "yes"}:
                            ready = True
                            break
                        print("Waiting. Type Y or YES when ready.")

                    log("Monitoring started. Press Ctrl+C to stop.")

                try:
                    # Check anything already visible before the first reload.
                    if process_available(page):
                        log("Reservation cycle completed.")
                        continue

                    # No availability: use the site's normal refresh control.
                    # There is no artificial polling sleep between refreshes.
                    reload_and_process(page)

                    # React immediately to the refreshed DOM.
                    if process_available(page):
                        log("Reservation cycle completed.")

                except Exception as exc:
                    log(f"Monitoring cycle error: {exc}")
                    log("Continuing with the next cycle.")
                    time.sleep(0.05)

        except KeyboardInterrupt:
            print()
            print("=" * 70)
            print("                    MONITOR STOPPED")
            print("=" * 70)
            print("Ctrl+C received. Closing the monitor cleanly.")
            print("=" * 70)

        except Exception as exc:
            log(f"Unexpected top-level error: {exc}")

        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
