"""
DOM Reservation Monitor
=======================

Browser-only, event-driven Playwright monitor.

Design goal:
- Use only what a normal logged-in browser can see.
- Do not access Cloudflare, D1, Worker code, Admin Log, or private server APIs.
- Do not repeatedly poll the DOM from Python.
- React to browser-visible DOM mutations as soon as they occur.
- Select all currently available matching cells in one browser-side operation.
- Continue indefinitely until Ctrl+C.

The website itself is responsible for receiving availability updates and
changing the DOM. The monitor simply observes those browser-visible changes.
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
RESERVED_BUTTON_SELECTOR = "#reserveButton"
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
# BROWSER-SIDE EVENT MONITORING
# ============================================================


def install_dom_observer(page) -> None:
    """Install a browser-side MutationObserver on the reservation grid."""
    page.evaluate(
        """
        () => {
            window.__rmMutationVersion = 0;
            window.__rmDomObserver?.disconnect();

            const grid = document.querySelector('#grid');
            if (!grid) throw new Error('Reservation grid #grid was not found.');

            window.__rmDomObserver = new MutationObserver(() => {
                window.__rmMutationVersion++;
            });

            window.__rmDomObserver.observe(grid, {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: ['class', 'data-cell-id'],
                characterData: true
            });
        }
        """
    )
    log("Browser-side DOM observer installed.")


def mutation_version(page) -> int:
    try:
        return int(page.evaluate("() => window.__rmMutationVersion || 0"))
    except Exception:
        return 0


def find_available_count(page) -> int:
    """Fast browser-side count of currently available cells."""
    try:
        locator = page.locator(f"{BLOCK_SELECTOR}.{AVAILABLE_CLASS}")
        count = locator.count()
        if TARGET_TEXT:
            return sum(
                1
                for index in range(count)
                if TARGET_TEXT.casefold() in (locator.nth(index).inner_text() or "").casefold()
            )
        return count
    except Exception as exc:
        log(f"Availability check failed: {exc}")
        return 0


def select_all_available(page) -> list[int]:
    """Select every matching available cell in one browser-side operation."""
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

                    // The page's normal click handler performs selection.
                    element.click();
                    selected.push(Number(element.dataset.cellId));
                }

                return selected;
            }
            """,
            TARGET_TEXT,
        )
        return [int(value) for value in ids if isinstance(value, (int, float))]
    except Exception as exc:
        log(f"Could not select available cells in one operation: {exc}")
        return []


def clear_reservation_message(page) -> None:
    try:
        page.locator(RESERVATION_MESSAGE_SELECTOR).evaluate(
            "element => { element.textContent = ''; }"
        )
    except Exception:
        pass


def reserve_selected(page) -> bool:
    """Click the normal reservation button and wait for a new response event."""
    try:
        button = page.locator(RESERVED_BUTTON_SELECTOR).first
        button.wait_for(state="visible", timeout=2_000)
        clear_reservation_message(page)

        log("Submitting all selected cells...")
        button.click()

        # No fixed sleep: wait for the browser-visible result to arrive.
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


def page_is_alive(page) -> bool:
    try:
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


def main() -> None:
    validate_settings()

    print()
    print("=" * 70)
    print("                 DOM RESERVATION MONITOR")
    print("=" * 70)
    print(f"URL:                 {URL}")
    print(f"Block selector:      {BLOCK_SELECTOR}")
    print(f"Available class:     {AVAILABLE_CLASS}")
    print(f"Reserve selector:    {RESERVED_BUTTON_SELECTOR}")
    print("Detection:           Browser DOM MutationObserver")
    print("Python polling:      DISABLED")
    print("Full page reloads:   DISABLED")
    print("Admin/log access:    DISABLED")
    print("Selection:           ALL matching cells in one browser operation")
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
                    print("The monitor will then react to browser-visible DOM changes.")
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

                    try:
                        install_dom_observer(page)
                    except Exception as exc:
                        log(f"Could not install DOM observer: {exc}")
                        ready = False
                        continue

                    log("Monitoring started. No Python polling or artificial scan delay is running.")

                try:
                    # First handle anything already available when the monitor starts.
                    available_count = find_available_count(page)
                    if available_count:
                        log(f"Detected {available_count} available matching cell(s).")
                        selected_ids = select_all_available(page)
                        if selected_ids:
                            log(f"Selected ALL {len(selected_ids)} matching cell(s): {selected_ids}")
                            reserve_selected(page)
                        else:
                            log("Available cells were detected but could not be selected.")

                    # From here on, sleep is replaced by a browser-side event wait.
                    version = mutation_version(page)
                    log("Waiting for the next browser-visible reservation-grid change...")

                    page.wait_for_function(
                        "(previous) => (window.__rmMutationVersion || 0) !== previous",
                        version,
                        timeout=30_000,
                    )

                except PlaywrightTimeoutError:
                    # A timeout here is not an error: it simply means the page
                    # produced no DOM mutation during this window. Re-arm the
                    # observer and wait again. No refresh button is clicked.
                    continue
                except Exception as exc:
                    log(f"Monitoring event error: {exc}")
                    time.sleep(0.2)

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
