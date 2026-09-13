"""
Sasol Transporters reservation monitor
======================================

Browser-realistic Playwright monitor for the authenticated Sasol Transporters
Unscheduled Orders / Active Slots page.

The monitor uses only the normal visible website controls. Login is performed
manually in the visible browser. It does not access private APIs, databases,
Cloudflare, or server-side interfaces.

Selection rule for this real-world adapter:
    Select ALL currently visible slots marked Available, then press Reserve.

The browser profile is persistent so an existing authenticated session can be
reused between runs.
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

BASE_URL = "https://www.sasoltransporters.com"
URL = f"{BASE_URL}/sasol2024/unscheduled-orders"

# Actual Sasol Transporters slot markup from the supplied authenticated HTML.
SLOT_SELECTOR = '.rz-timeslot[title="Available"]'
TIMESLOT_WRAPPER_SELECTOR = ".rz-timeslots-wrapper"

# The page has separate desktop/mobile copies of some controls. We always use
# the visible one instead of relying on generated Blazor/Radzen element IDs.
RESERVE_BUTTON_TEXT = "Reserve"
REFRESH_ICON_TEXT = "refresh"

PAGE_LOAD_TIMEOUT = 15_000
DOM_UPDATE_TIMEOUT = 3_000
ACTION_TIMEOUT = 3_000
RESERVATION_RESULT_TIMEOUT = 5_000
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


def visible_slots(page):
    """Return visible Available slots only.

    The real page renders desktop and mobile markup. Filtering by visibility
    prevents us from clicking both copies of the same slot.
    """
    locator = page.locator(SLOT_SELECTOR)
    result = []
    for index in range(locator.count()):
        slot = locator.nth(index)
        try:
            if slot.is_visible():
                result.append(slot)
        except Exception:
            continue
    return result


def slot_signature(page) -> str:
    """Return a browser-visible signature of all visible slot states."""
    return page.locator(".rz-timeslot").evaluate_all(
        """
        elements => elements
            .filter(e => {
                const r = e.getBoundingClientRect();
                const s = getComputedStyle(e);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
            })
            .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`)
            .join('|')
        """
    )


def wait_for_grid_update(page, previous_signature: str) -> bool:
    """Wait for the normal refresh action to visibly change the slot grid."""
    try:
        page.wait_for_function(
            """
            previous => {
                const current = [...document.querySelectorAll('.rz-timeslot')]
                    .filter(e => {
                        const r = e.getBoundingClientRect();
                        const s = getComputedStyle(e);
                        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                    })
                    .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`)
                    .join('|');
                return current !== previous;
            }
            """,
            previous_signature,
            timeout=DOM_UPDATE_TIMEOUT,
        )
        return True
    except PlaywrightTimeoutError:
        return False


def visible_button_with_text(page, text: str):
    """Find the first visible button containing the requested text."""
    buttons = page.locator("button")
    for index in range(buttons.count()):
        button = buttons.nth(index)
        try:
            if button.is_visible() and text.casefold() in button.inner_text().casefold():
                return button
        except Exception:
            continue
    return None


def visible_refresh_button(page):
    """Find the visible Radzen refresh button by its stable icon text."""
    buttons = page.locator("button")
    for index in range(buttons.count()):
        button = buttons.nth(index)
        try:
            if not button.is_visible():
                continue
            if REFRESH_ICON_TEXT.casefold() in button.inner_text().casefold():
                return button
        except Exception:
            continue
    return None


def describe_slot(slot) -> str:
    """Return date/hour information from the slot's date wrapper."""
    try:
        hour = (slot.inner_text() or "").strip()
        wrapper = slot.locator(
            "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' rz-timeslots-wrapper ')]"
        ).first
        date_text = (wrapper.locator(".rz-timeslots-date").inner_text() or "").strip()
        if date_text:
            return f"{date_text} {hour}:00"
        return hour
    except Exception:
        try:
            return (slot.inner_text() or "").strip()
        except Exception:
            return "unknown slot"


def select_all_available(page) -> list[str]:
    """Click every visible Available slot in one browser-side operation.

    The supplied real page uses title="Available" rather than the simulator's
    .booking-block.available markup. We deliberately filter to the visible
    copy because the Blazor page contains both desktop and mobile renderings.
    """
    try:
        selected = page.locator(SLOT_SELECTOR).evaluate_all(
            """
            elements => {
                const selected = [];
                for (const element of elements) {
                    const rect = element.getBoundingClientRect();
                    const style = getComputedStyle(element);
                    const visible = rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' && style.display !== 'none';
                    if (!visible || element.title !== 'Available') continue;

                    const wrapper = element.closest('.rz-timeslots-wrapper');
                    const date = wrapper?.querySelector('.rz-timeslots-date')?.textContent?.trim() || '';
                    const hour = element.textContent?.trim() || '';
                    element.click();
                    selected.push(`${date} ${hour}:00`.trim());
                }
                return selected;
            }
            """
        )
        return [str(value) for value in selected]
    except Exception as exc:
        log(f"Could not select available slots: {exc}")
        return []


def visible_dialog_text(page) -> str:
    """Read the text of the visible Radzen dialog, if one exists."""
    dialogs = page.locator(".rz-dialog[role='dialog']")
    for index in range(dialogs.count()):
        dialog = dialogs.nth(index)
        try:
            if dialog.is_visible():
                return (dialog.inner_text() or "").strip()
        except Exception:
            continue
    return ""


def dismiss_visible_dialog(page) -> None:
    """Close a visible Radzen dialog using its normal close/OK control."""
    try:
        dialogs = page.locator(".rz-dialog[role='dialog']")
        for index in range(dialogs.count()):
            dialog = dialogs.nth(index)
            if not dialog.is_visible():
                continue

            for label in ("OK", "Close"):
                buttons = dialog.get_by_role("button", name=label, exact=True)
                if buttons.count():
                    buttons.first.click(timeout=1_000)
                    return

            close = dialog.locator(".rz-dialog-titlebar-close")
            if close.count() and close.first.is_visible():
                close.first.click(timeout=1_000)
                return
    except Exception:
        pass


def reserve_selected(page, expected_count: int) -> bool:
    """Press the real Reserve button and report the browser-visible outcome."""
    button = visible_button_with_text(page, RESERVE_BUTTON_TEXT)
    if button is None:
        log("ERROR: Visible Reserve button was not found.")
        return False

    before_signature = slot_signature(page)

    try:
        log(f"Submitting {expected_count} selected slot(s)...")
        button.click(timeout=ACTION_TIMEOUT)
    except Exception as exc:
        log(f"ERROR clicking Reserve: {exc}")
        return False

    deadline = time.monotonic() + RESERVATION_RESULT_TIMEOUT / 1000
    while time.monotonic() < deadline:
        dialog_text = visible_dialog_text(page)
        if dialog_text:
            lowered = dialog_text.casefold()
            if any(
                phrase in lowered
                for phrase in ("no longer available", "error", "failed", "not available")
            ):
                log(f"Website reservation response: {dialog_text}")
                dismiss_visible_dialog(page)
                return False

            log(f"Website dialog response: {dialog_text}")
            dismiss_visible_dialog(page)
            return True

        try:
            after_signature = slot_signature(page)
            if after_signature != before_signature:
                log("Reservation action changed the visible slot grid.")
                return True
        except Exception:
            pass

        time.sleep(0.05)

    log("No explicit reservation confirmation was visible after Reserve.")
    return False


def reload_availability(page) -> None:
    """Press the site's normal visible refresh control."""
    previous_signature = slot_signature(page)
    refresh = visible_refresh_button(page)
    if refresh is None:
        raise RuntimeError("Visible refresh button was not found")

    start = time.perf_counter()
    refresh.click(timeout=ACTION_TIMEOUT)
    log("Reload Availability clicked.")

    changed = wait_for_grid_update(page, previous_signature)
    elapsed_ms = (time.perf_counter() - start) * 1000

    if changed:
        log(f"Visible slot grid changed after reload ({elapsed_ms:.1f} ms).")
    else:
        log(f"No visible slot-grid change within {DOM_UPDATE_TIMEOUT} ms ({elapsed_ms:.1f} ms).")


def process_available(page) -> bool:
    """Select ALL visible Available slots and submit them together."""
    slots = visible_slots(page)
    if not slots:
        return False

    descriptions = []
    for slot in slots:
        descriptions.append(describe_slot(slot))

    log(f"Found {len(slots)} available slot(s): {descriptions}")

    selected = select_all_available(page)
    if not selected:
        log("Available slots were found but none could be selected.")
        return False

    log(f"Selected ALL {len(selected)} available slot(s): {selected}")
    return reserve_selected(page, len(selected))


# ============================================================
# MAIN
# ============================================================


def main() -> None:
    print()
    print("=" * 72)
    print("              SASOL TRANSPORTERS RESERVATION MONITOR")
    print("=" * 72)
    print(f"URL:                 {URL}")
    print(f"Available selector:  {SLOT_SELECTOR}")
    print("Selection:           ALL currently visible Available slots")
    print("Refresh:             Normal visible refresh button")
    print("Login:               Manual in visible browser")
    print("Privileged APIs:     DISABLED")
    print("Full page reloads:   DISABLED")
    print("Runtime:             Continuous until Ctrl+C")
    print("=" * 72)
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
            page.set_default_timeout(ACTION_TIMEOUT)
            ready = False

            while True:
                if not page_is_alive(page):
                    log("Browser page is unavailable. Opening a replacement page...")
                    page = context.new_page()
                    page.set_default_timeout(ACTION_TIMEOUT)
                    ready = False

                try:
                    if page.url == "about:blank":
                        log("Opening Sasol Transporters...")
                        page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                except Exception as exc:
                    log(f"Could not open/navigate page: {exc}")
                    time.sleep(1)
                    continue

                if not ready:
                    print()
                    print("=" * 72)
                    print("                         LOGIN / READY")
                    print("=" * 72)
                    print("Log in manually if required and open Unscheduled Orders > Active Slots.")
                    print("Make sure the Active Slots grid is visible.")
                    print("Type Y or YES when ready to start monitoring.")
                    print("The monitor will select ALL visible Available slots and press Reserve.")
                    print("=" * 72)
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
                    if process_available(page):
                        log("Reservation cycle completed.")
                        continue

                    reload_availability(page)

                    if process_available(page):
                        log("Reservation cycle completed.")

                except Exception as exc:
                    log(f"Monitoring cycle error: {exc}")
                    log("Continuing with the next cycle.")
                    time.sleep(0.05)

        except KeyboardInterrupt:
            print()
            print("=" * 72)
            print("                    MONITOR STOPPED")
            print("=" * 72)
            print("Ctrl+C received. Closing the monitor cleanly.")
            print("=" * 72)

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
