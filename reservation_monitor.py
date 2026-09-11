"""
DOM Reservation Monitor
=======================

A configurable Playwright monitor for pages containing repeated
availability/booking blocks.

The browser remains visible. Authentication and CAPTCHA are manual:
the program never attempts to solve or bypass CAPTCHA.

Configure the SETTINGS section below, then run:
    py reservation_monitor.py
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# SETTINGS
# ============================================================

URL = "https://reservation-monitor-test.ronaldjennings84.workers.dev/"
LOGIN_TIME_SECONDS = 120
BLOCK_SELECTOR = ".booking-block"
TARGET_TEXT = ""
AVAILABLE_CLASS = "available"
USE_WHITE_BACKGROUND = True
WHITE_RGB = "rgb(255, 255, 255)"
RESERVED_BUTTON_SELECTOR = "#reserveButton"
REFRESH_BUTTON_SELECTOR = "#reloadGrid"
RESERVATION_MESSAGE_SELECTOR = "#message"
RESERVATION_SUCCESS_TEXT = "Reserved cells:"
CHECK_INTERVAL = 1.0
PAGE_LOAD_TIMEOUT = 15_000
DEBUG = True
KEEP_BROWSER_OPEN_AFTER_SUCCESS = True
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
        return block.inner_text(timeout=1_000).strip()
    except Exception:
        return ""


def is_white_background(block) -> bool:
    try:
        colour = block.evaluate(
            "element => getComputedStyle(element).backgroundColor"
        )
        return colour == WHITE_RGB
    except Exception:
        return False


def is_available(block) -> bool:
    if AVAILABLE_CLASS:
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


def find_matching_block(page):
    blocks = page.locator(BLOCK_SELECTOR)
    count = blocks.count()

    if DEBUG:
        log(f"Found {count} blocks")

    for index in range(count):
        block = blocks.nth(index)

        try:
            if not is_available(block):
                continue
            if not matches_target(block):
                continue

            text = block_text(block)
            log(
                f"MATCH FOUND - block {index + 1}"
                + (f": {text[:120]}" if text else "")
            )
            return block, index
        except Exception as exc:
            if DEBUG:
                log(f"Could not inspect block {index + 1}: {exc}")

    return None, None


def click_reserved(page) -> bool:
    log("Looking for Reserve button...")

    try:
        message = page.locator(RESERVATION_MESSAGE_SELECTOR)
        message.wait_for(state="visible", timeout=5_000)
        message_text_before = message.inner_text().strip()
        if DEBUG and message_text_before:
            log(f"Reservation message before click: {message_text_before}")

        button = page.locator(RESERVED_BUTTON_SELECTOR).first
        button.wait_for(state="visible", timeout=5_000)
        log("Reserve button found.")
        button.click()
        log("Reserve button clicked. Waiting for the website to confirm success...")

        # A button click alone is not enough to call the reservation successful.
        # The simulator writes to D1 and then updates #message with the result.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            text = message.inner_text().strip()
            if text.startswith(RESERVATION_SUCCESS_TEXT):
                log(f"Website confirmed reservation: {text}")
                return True
            if text and text != message_text_before:
                log(f"Website reservation response: {text}")
                return False
            time.sleep(0.1)

        log("ERROR: Reserve button was clicked, but the website did not confirm a successful reservation.")
        return False

    except PlaywrightTimeoutError:
        log("ERROR: Reserve button or reservation message did not appear within 5 seconds.")
        return False
    except Exception as exc:
        log(f"ERROR clicking Reserve: {exc}")
        return False


def refresh_availability(page) -> bool:
    if REFRESH_BUTTON_SELECTOR:
        try:
            button = page.locator(REFRESH_BUTTON_SELECTOR).first
            button.wait_for(state="visible", timeout=5_000)
            button.click()
            return True
        except PlaywrightTimeoutError:
            log("ERROR: Refresh Availability button did not appear within 5 seconds.")
            return False
        except Exception as exc:
            log(f"Refresh button error: {exc}")
            return False

    try:
        page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        return True
    except PlaywrightTimeoutError:
        log("Page reload timed out; continuing with current page.")
        return False
    except Exception as exc:
        log(f"Refresh error: {exc}")
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
    print(f"Login period:        {LOGIN_TIME_SECONDS} seconds")
    print(f"Cycle target:        {CHECK_INTERVAL:.2f} seconds")
    print(f"Block selector:      {BLOCK_SELECTOR}")
    print(f"Available class:     {AVAILABLE_CLASS or '(disabled)'}")
    print(f"White detection:     {USE_WHITE_BACKGROUND}")
    print(f"Reserve selector:    {RESERVED_BUTTON_SELECTOR}")
    print(f"Refresh selector:    {REFRESH_BUTTON_SELECTOR or '(full page reload)'}")
    print("=" * 64)
    print()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(5_000)

        try:
            log("Opening website...")
            page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        except Exception as exc:
            log(f"Could not open website: {exc}")
            context.close()
            sys.exit(1)

        print()
        print("=" * 64)
        print("                         LOGIN PERIOD")
        print("=" * 64)
        print("Please log in and complete any CAPTCHA manually.")
        print("Then navigate to the Reservations page.")
        print()
        print(f"You have {LOGIN_TIME_SECONDS} seconds.")
        print("=" * 64)
        print()

        login_start = time.monotonic()
        while True:
            remaining = LOGIN_TIME_SECONDS - (time.monotonic() - login_start)
            if remaining <= 0:
                break
            print(f"\rTime remaining: {int(remaining):3d} seconds", end="", flush=True)
            time.sleep(1)

        print("\n")
        print("=" * 64)
        print("                       READY TO START")
        print("=" * 64)
        print("Make sure the browser is on the Reservations page.")
        input("Press ENTER to start monitoring...")
        print()

        cycle = 0

        while True:
            cycle += 1
            cycle_start = time.monotonic()
            log(f"Cycle {cycle}: checking page...")

            try:
                block, index = find_matching_block(page)

                if block is not None:
                    print()
                    print("=" * 64)
                    print("                  AVAILABLE BLOCK FOUND")
                    print("=" * 64)
                    print()
                    log(f"Block number: {index + 1}")
                    log("Clicking matching block...")

                    block.scroll_into_view_if_needed()
                    block.click()
                    log("Block clicked.")

                    if click_reserved(page):
                        print()
                        print("=" * 64)
                        print("                  RESERVATION ACTION COMPLETE")
                        print("=" * 64)
                        print()
                        log("Website confirmed the reservation was recorded.")

                        if KEEP_BROWSER_OPEN_AFTER_SUCCESS:
                            print("The browser will remain open so you can inspect the reservation.")
                            input("Press ENTER only when you want to close the browser...")
                        break

                    log("Reservation was NOT confirmed by the website.")
                    log("Stopping to prevent an unintended repeated action.")
                    print("Please inspect the browser and the Admin Log before continuing.")
                    input("Press ENTER to close the browser...")
                    break

                log("No matching available block.")

            except Exception as exc:
                log(f"Cycle error: {exc}")

            elapsed = time.monotonic() - cycle_start
            log(f"Cycle completed in {elapsed:.3f} seconds")

            wait_time = CHECK_INTERVAL - elapsed
            if wait_time > 0:
                time.sleep(wait_time)

            refresh_start = time.monotonic()
            log("Refreshing availability...")

            if refresh_availability(page):
                log(
                    "Availability refresh completed in "
                    f"{time.monotonic() - refresh_start:.3f} seconds"
                )

        context.close()


if __name__ == "__main__":
    main()
