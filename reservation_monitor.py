"""
DOM Reservation Monitor
=======================

Fast Playwright monitor for the reservation simulator.

The browser remains visible. Authentication and CAPTCHA are manual:
the program never attempts to solve or bypass CAPTCHA.

The monitor runs continuously until you stop it with Ctrl+C.
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
USE_WHITE_BACKGROUND = True
WHITE_RGB = "rgb(255, 255, 255)"
RESERVED_BUTTON_SELECTOR = "#reserveButton"
REFRESH_BUTTON_SELECTOR = "#reloadGrid"
RESERVATION_MESSAGE_SELECTOR = "#message"
RESERVATION_SUCCESS_TEXT = "Reserved cells:"

# Fast mode: check 10 times per second. The simulator itself changes
# availability every 30 seconds, so checking faster than this adds little
# benefit while creating more browser/worker traffic.
CHECK_INTERVAL = 0.10

PAGE_LOAD_TIMEOUT = 15_000
DEBUG = False
PROFILE_DIR = Path(".browser-profile")


# ============================================================
# LOGGING
# ============================================================


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(message: str) -> None:
    print(f"[{timestamp()}] {message}", flush=True)


# ============================================================
# DOM HELPERS
# ============================================================


def block_text(block) -> str:
    try:
        return block.inner_text(timeout=500).strip()
    except Exception:
        return ""


def is_white_background(block) -> bool:
    try:
        colour = block.evaluate("element => getComputedStyle(element).backgroundColor")
        return colour == WHITE_RGB
    except Exception:
        return False


def is_available(block) -> bool:
    try:
        classes = (block.get_attribute("class") or "").split()
        if AVAILABLE_CLASS in classes:
            return True
    except Exception:
        pass

    if USE_WHITE_BACKGROUND and is_white_background(block):
        return True

    return False


def matches_target(block) -> bool:
    if not TARGET_TEXT:
        return True
    return TARGET_TEXT.casefold() in block_text(block).casefold()


def find_matching_blocks(page):
    """Return every currently available matching block."""
    blocks = page.locator(BLOCK_SELECTOR)
    count = blocks.count()
    matches = []

    for index in range(count):
        try:
            block = blocks.nth(index)
            if not is_available(block):
                continue
            if not matches_target(block):
                continue

            text = block_text(block)
            if DEBUG:
                log(
                    f"AVAILABLE MATCH - block {index + 1}"
                    + (f": {text[:120]}" if text else "")
                )
            matches.append((block, index))
        except Exception as exc:
            if DEBUG:
                log(f"Could not inspect block {index + 1}: {exc}")

    return matches


def get_reservation_message(page) -> str:
    try:
        return page.locator(RESERVATION_MESSAGE_SELECTOR).inner_text(timeout=500).strip()
    except Exception:
        return ""


def click_reserved(page) -> bool:
    """Click Reserve Selected and verify the site's response."""
    try:
        button = page.locator(RESERVED_BUTTON_SELECTOR).first
        button.wait_for(state="visible", timeout=2_000)

        before = get_reservation_message(page)
        button.click()

        # Check immediately, then very briefly for the async response.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            text = get_reservation_message(page)

            if text.startswith(RESERVATION_SUCCESS_TEXT):
                log(f"Reservation confirmed: {text}")
                return True

            if text and text != before:
                log(f"Reservation response: {text}")
                return False

            time.sleep(0.01)

        log("No reservation confirmation received within 2 seconds.")
        return False

    except PlaywrightTimeoutError:
        log("Reserve button did not appear; continuing.")
        return False
    except Exception as exc:
        log(f"ERROR clicking Reserve: {exc}; continuing.")
        return False


def refresh_availability(page) -> bool:
    """Refresh availability without navigating away from the page."""
    try:
        button = page.locator(REFRESH_BUTTON_SELECTOR).first
        button.click(timeout=1_000)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception as exc:
        if DEBUG:
            log(f"Refresh error: {exc}")
        return False


def page_is_alive(page) -> bool:
    try:
        _ = page.url
        return not page.is_closed()
    except Exception:
        return False


# ============================================================
# MAIN
# ============================================================


def validate_settings() -> None:
    if "YOUR-WEBSITE-HERE" in URL:
        print("ERROR: Change URL in the SETTINGS section.")
        sys.exit(1)
    if "YOUR-BLOCK-SELECTOR" in BLOCK_SELECTOR:
        print("ERROR: Change BLOCK_SELECTOR in the SETTINGS section.")
        sys.exit(1)
    if CHECK_INTERVAL <= 0:
        print("ERROR: CHECK_INTERVAL must be greater than zero.")
        sys.exit(1)


def main() -> None:
    validate_settings()

    print()
    print("=" * 64)
    print("                 DOM RESERVATION MONITOR")
    print("=" * 64)
    print(f"URL:                 {URL}")
    print(f"Check interval:      {CHECK_INTERVAL:.2f} seconds")
    print(f"Block selector:      {BLOCK_SELECTOR}")
    print(f"Available class:     {AVAILABLE_CLASS or '(disabled)'}")
    print(f"White detection:     {USE_WHITE_BACKGROUND}")
    print(f"Reserve selector:    {RESERVED_BUTTON_SELECTOR}")
    print(f"Refresh selector:    {REFRESH_BUTTON_SELECTOR}")
    print("Mode:                FAST - Reserve ALL matching available cells")
    print("Runtime:             Continuous until Ctrl+C")
    print("=" * 64)
    print()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = None
        ready = False

        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1400, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(2_000)

            while True:
                # ----------------------------------------------------
                # Recover if the browser page disappears.
                # ----------------------------------------------------
                if not page_is_alive(page):
                    log("Browser page unavailable. Attempting recovery...")
                    try:
                        page = context.new_page()
                        page.set_default_timeout(2_000)
                        page.goto(
                            URL,
                            wait_until="domcontentloaded",
                            timeout=PAGE_LOAD_TIMEOUT,
                        )
                        ready = False
                    except Exception as exc:
                        log(f"Recovery failed: {exc}; retrying.")
                        time.sleep(1)
                        continue

                # ----------------------------------------------------
                # Open the site once if the browser starts blank.
                # ----------------------------------------------------
                try:
                    if page.url == "about:blank":
                        log("Opening website...")
                        page.goto(
                            URL,
                            wait_until="domcontentloaded",
                            timeout=PAGE_LOAD_TIMEOUT,
                        )
                except Exception as exc:
                    log(f"Could not open/navigate page: {exc}; retrying.")
                    time.sleep(1)
                    continue

                # ----------------------------------------------------
                # Manual login/readiness happens once per run.
                # ----------------------------------------------------
                if not ready:
                    print()
                    print("=" * 64)
                    print("                         LOGIN / READY")
                    print("=" * 64)
                    print("The browser is open.")
                    print("Log in manually if needed, then navigate to the Reservations page.")
                    print("Type Y or YES when you are ready to start FAST monitoring.")
                    print("The monitor will then run continuously until Ctrl+C.")
                    print("=" * 64)
                    print()

                    while True:
                        try:
                            answer = input("Are you ready to start monitoring? [Y/N]: ").strip().casefold()
                        except EOFError:
                            answer = ""

                        if answer in {"y", "yes"}:
                            ready = True
                            break

                        print("Waiting. Type Y or YES when you are ready.")

                    log("FAST monitoring started. Press Ctrl+C to stop.")

                # ----------------------------------------------------
                # One very fast protected monitoring cycle.
                # ----------------------------------------------------
                cycle_start = time.monotonic()

                try:
                    matches = find_matching_blocks(page)

                    if matches:
                        log(f"FOUND {len(matches)} available cell(s) - selecting ALL immediately.")

                        selected = 0
                        for block, index in matches:
                            try:
                                # Do not scroll: scrolling is unnecessary and slower.
                                block.click(timeout=500, force=True)
                                selected += 1
                            except Exception as exc:
                                if DEBUG:
                                    log(f"Could not select block {index + 1}: {exc}")

                        if selected:
                            log(f"Selected {selected} cell(s) - clicking Reserve Selected immediately.")
                            click_reserved(page)

                    # Refresh availability so newly available cells are visible.
                    refresh_availability(page)

                except Exception as exc:
                    log(f"Monitoring cycle error: {exc}; continuing immediately.")

                # ----------------------------------------------------
                # Keep the target interval without adding an unnecessary
                # full second of waiting after fast cycles.
                # ----------------------------------------------------
                elapsed = time.monotonic() - cycle_start
                wait_time = max(0.0, CHECK_INTERVAL - elapsed)
                if wait_time:
                    time.sleep(wait_time)

        except KeyboardInterrupt:
            print()
            print("=" * 64)
            print("                    MONITOR STOPPED")
            print("=" * 64)
            print("Ctrl+C received. Closing the monitor cleanly.")
            print("=" * 64)

        except Exception as exc:
            log(f"Unexpected top-level error: {exc}")
            log("Monitor encountered an unexpected problem.")

        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
