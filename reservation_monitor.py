"""
DOM Reservation Monitor
=======================

Playwright-based reservation monitor for the test simulator.

The browser stays visible and login is always manual. The monitor is
intentionally defensive: transient DOM, refresh, or network errors are
caught and the monitoring loop continues instead of terminating.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


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
CHECK_INTERVAL = 1.0
PAGE_LOAD_TIMEOUT = 15_000
DEBUG = True
KEEP_BROWSER_OPEN_AFTER_SUCCESS = True
PROFILE_DIR = Path(".browser-profile")

# Recovery settings.
ERROR_RETRY_DELAY = 2.0
REFRESH_RETRY_DELAY = 2.0


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
    try:
        if AVAILABLE_CLASS:
            classes = (block.get_attribute("class") or "").split()
            if AVAILABLE_CLASS in classes:
                return True

        if USE_WHITE_BACKGROUND and is_white_background(block):
            return True
    except Exception as exc:
        if DEBUG:
            log(f"Availability check failed: {exc}")

    return False


def matches_target(block) -> bool:
    if not TARGET_TEXT:
        return True
    try:
        return TARGET_TEXT.casefold() in block_text(block).casefold()
    except Exception:
        return False


def find_matching_blocks(page):
    """Return every currently available matching block."""
    try:
        blocks = page.locator(BLOCK_SELECTOR)
        count = blocks.count()
    except Exception as exc:
        log(f"Could not read reservation blocks: {exc}")
        return []

    matches = []

    if DEBUG:
        log(f"Found {count} blocks")

    for index in range(count):
        try:
            block = blocks.nth(index)
            if not is_available(block):
                continue
            if not matches_target(block):
                continue

            text = block_text(block)
            log(
                f"AVAILABLE MATCH - block {index + 1}"
                + (f": {text[:120]}" if text else "")
            )
            matches.append((block, index))
        except Exception as exc:
            # One bad DOM element must never kill the whole monitoring cycle.
            log(f"Could not inspect block {index + 1}: {exc}")

    return matches


def select_blocks(matches) -> list[int]:
    """Select all matches; skip individual cells that fail to click."""
    selected = []

    for block, index in matches:
        try:
            block.scroll_into_view_if_needed(timeout=3_000)
            block.click(timeout=3_000)
            selected.append(index + 1)
            log(f"Selected block {index + 1}.")
        except Exception as exc:
            log(f"Could not select block {index + 1}: {exc}")

    return selected


def click_reserved(page) -> tuple[bool, str]:
    """Click Reserve Selected and wait for a definite website response."""
    log("Looking for Reserve button...")

    try:
        button = page.locator(RESERVED_BUTTON_SELECTOR).first
        button.wait_for(state="visible", timeout=5_000)

        message = page.locator(RESERVATION_MESSAGE_SELECTOR)
        message_text_before = message.inner_text().strip()

        log("Reserve button found.")
        button.click()
        log("Reserve button clicked. Waiting for website confirmation...")

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                text = message.inner_text().strip()
            except Exception:
                text = ""

            if text.startswith(RESERVATION_SUCCESS_TEXT):
                log(f"Website confirmed reservation: {text}")
                return True, text

            if text and text != message_text_before:
                log(f"Website reservation response: {text}")
                return False, text

            time.sleep(0.1)

        # The click happened, but we received no response. Do NOT blindly
        # click again because the server may have accepted the first request.
        log("WARNING: Reserve was clicked but no confirmation was received.")
        return False, "unknown"

    except PlaywrightTimeoutError:
        log("WARNING: Reserve button did not appear within 5 seconds.")
        return False, "button-timeout"
    except Exception as exc:
        log(f"WARNING: Reserve action encountered an error: {exc}")
        return False, "exception"


def verify_cells_no_longer_available(page, cell_ids: list[int]) -> bool:
    """For the simulator, check whether selected cells changed to unavailable."""
    if not cell_ids:
        return False

    try:
        result = page.evaluate(
            """
            async (ids) => {
                const token = sessionStorage.getItem('rm_session_token');
                const response = await fetch('/api/state', {
                    headers: token ? { Authorization: `Bearer ${token}` } : {}
                });
                if (!response.ok) return null;
                const data = await response.json();
                return data.cells
                    .filter(c => ids.includes(Number(c.id)))
                    .map(c => ({id: Number(c.id), status: c.status}));
            }
            """,
            cell_ids,
        )

        if not result or len(result) != len(cell_ids):
            return False

        unavailable = all(cell["status"] != "available" for cell in result)
        if unavailable:
            log(
                "The selected cells are no longer available. "
                "The reservation request may have succeeded despite the missing response."
            )
        return unavailable
    except Exception as exc:
        if DEBUG:
            log(f"Could not verify cell state after uncertain reservation: {exc}")
        return False


def refresh_availability(page) -> bool:
    """Refresh availability without killing the monitoring loop."""
    try:
        if REFRESH_BUTTON_SELECTOR:
            button = page.locator(REFRESH_BUTTON_SELECTOR).first
            button.wait_for(state="visible", timeout=5_000)
            button.click(timeout=5_000)
            return True

        page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        return True

    except PlaywrightTimeoutError as exc:
        log(f"Refresh timed out; monitoring will continue: {exc}")
    except Exception as exc:
        log(f"Refresh failed; monitoring will continue: {exc}")

    return False


# ============================================================
# STARTUP / MAIN
# ============================================================


def validate_settings() -> None:
    if "YOUR-WEBSITE-HERE" in URL:
        print("ERROR: URL has not been configured.")
        sys.exit(1)
    if "YOUR-BLOCK-SELECTOR" in BLOCK_SELECTOR:
        print("ERROR: BLOCK_SELECTOR has not been configured.")
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
    print(f"Cycle target:        {CHECK_INTERVAL:.2f} seconds")
    print(f"Block selector:      {BLOCK_SELECTOR}")
    print(f"Available class:     {AVAILABLE_CLASS or '(disabled)'}")
    print(f"White detection:     {USE_WHITE_BACKGROUND}")
    print(f"Reserve selector:    {RESERVED_BUTTON_SELECTOR}")
    print(f"Refresh selector:    {REFRESH_BUTTON_SELECTOR or '(full page reload)'}")
    print("Mode:                Reserve ALL matching available cells")
    print("Recovery:             Errors are caught and monitoring continues")
    print("=" * 64)
    print()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1400, "height": 900},
            )
        except Exception as exc:
            log(f"Could not start Chromium: {exc}")
            return

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(5_000)

            try:
                log("Opening website...")
                page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            except Exception as exc:
                log(f"Could not open website: {exc}")
                log("The browser will remain open so you can inspect it.")
                input("Press ENTER to close the browser...")
                return

            print()
            print("=" * 64)
            print("                         LOGIN / READY")
            print("=" * 64)
            print("The browser is open.")
            print("Log in manually if needed, then navigate to the Reservations page.")
            print("When you are ready for the monitor to start, type Y and press ENTER.")
            print("You can also type YES. Any other answer will keep waiting.")
            print("=" * 64)
            print()

            while True:
                try:
                    answer = input("Are you ready to start monitoring? [Y/N]: ").strip().casefold()
                except (EOFError, KeyboardInterrupt):
                    print()
                    log("Input interrupted. Browser will remain open.")
                    return

                if answer in {"y", "yes"}:
                    break
                print("Waiting. Type Y or YES when you are ready.")

            log("Monitoring started.")
            cycle = 0

            while True:
                cycle += 1
                cycle_start = time.monotonic()

                try:
                    log(f"Cycle {cycle}: checking page...")
                    matches = find_matching_blocks(page)

                    if matches:
                        print()
                        print("=" * 64)
                        print("               AVAILABLE BLOCKS FOUND")
                        print("=" * 64)
                        print()

                        log(f"Found {len(matches)} matching available cell(s).")
                        log("Selecting ALL matching available cells...")
                        selected_ids = select_blocks(matches)

                        if not selected_ids:
                            log("No cells could be selected. Continuing monitoring.")
                        else:
                            log(
                                f"Selected {len(selected_ids)} cell(s): "
                                f"{', '.join(map(str, selected_ids))}"
                            )
                            log("Clicking Reserve Selected...")

                            success, response = click_reserved(page)

                            if success:
                                print()
                                print("=" * 64)
                                print("              RESERVATION ACTION COMPLETE")
                                print("=" * 64)
                                print()
                                log("Website confirmed all selected reservations were recorded.")

                                if KEEP_BROWSER_OPEN_AFTER_SUCCESS:
                                    print("The browser will remain open so you can inspect the reservations.")
                                    try:
                                        input("Press ENTER only when you want to close the browser...")
                                    except (EOFError, KeyboardInterrupt):
                                        pass
                                return

                            if response == "unknown":
                                # Avoid a duplicate click if the first request actually
                                # reached the Worker but its response was lost.
                                if verify_cells_no_longer_available(page, selected_ids):
                                    log("Treating the uncertain request as completed; continuing safely.")
                                    if KEEP_BROWSER_OPEN_AFTER_SUCCESS:
                                        print("The browser will remain open so you can inspect the reservations.")
                                        try:
                                            input("Press ENTER only when you want to close the browser...")
                                        except (EOFError, KeyboardInterrupt):
                                            pass
                                    return

                            # A definite failure or an uncertain result where the
                            # selected cells are still available. Clear the selection
                            # through a grid refresh and continue instead of killing
                            # the whole program.
                            log("Reservation was not confirmed. Refreshing and continuing monitoring.")

                except PlaywrightTimeoutError as exc:
                    log(f"Transient Playwright timeout: {exc}")
                    log("Monitoring continues after a short retry delay.")
                except Exception as exc:
                    # This is the main safety net: unexpected cycle errors must not
                    # terminate the monitor.
                    log(f"Unexpected cycle error: {exc}")
                    log("Monitoring continues after a short retry delay.")

                elapsed = time.monotonic() - cycle_start
                wait_time = CHECK_INTERVAL - elapsed
                if wait_time > 0:
                    time.sleep(wait_time)

                try:
                    log("Refreshing availability...")
                    if refresh_availability(page):
                        log("Availability refresh completed.")
                    else:
                        log(
                            f"Refresh unsuccessful. Retrying after {REFRESH_RETRY_DELAY:.1f} seconds."
                        )
                        time.sleep(REFRESH_RETRY_DELAY)
                except Exception as exc:
                    # Even the refresh path has its own safety net.
                    log(f"Unexpected refresh error: {exc}")
                    time.sleep(REFRESH_RETRY_DELAY)

        except (KeyboardInterrupt, EOFError):
            log("Monitor stopped by user. Browser will remain open until this program closes it.")
        except Exception as exc:
            log(f"Unexpected monitor error: {exc}")
            log("The browser will remain open for inspection.")
            try:
                input("Press ENTER to close the browser...")
            except (EOFError, KeyboardInterrupt):
                pass
        finally:
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
