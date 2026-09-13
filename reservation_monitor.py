"""Sasol Transporters - observation-only available-slot test."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.sasoltransporters.com/sasol2024/"
SLOT_SELECTOR = '.rz-timeslot[title="Available"]'
PROFILE_DIR = Path(".browser-profile")
ACTION_TIMEOUT = 3000
PAGE_LOAD_TIMEOUT = 15000


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def visible_available_slots(page):
    slots = page.locator(SLOT_SELECTOR)
    result = []
    for i in range(slots.count()):
        slot = slots.nth(i)
        try:
            if slot.is_visible():
                result.append(slot)
        except Exception:
            pass
    return result


def describe_slot(slot) -> str:
    try:
        hour = (slot.inner_text() or "").strip()
        wrapper = slot.locator(
            "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' rz-timeslots-wrapper ')]"
        ).first
        date_text = (wrapper.locator(".rz-timeslots-date").inner_text() or "").strip()
        return f"{date_text} {hour}:00" if date_text else hour
    except Exception:
        return "unknown date/time"


def slot_signature(page) -> str:
    return page.locator(".rz-timeslot").evaluate_all(
        """
        elements => elements.filter(e => {
            const r=e.getBoundingClientRect(), s=getComputedStyle(e);
            return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
        }).map(e => `${e.title}:${e.className}:${e.textContent.trim()}`).join('|')
        """
    )


def refresh(page) -> None:
    before = slot_signature(page)
    buttons = page.locator("button")
    refresh_button = None
    for i in range(buttons.count()):
        button = buttons.nth(i)
        try:
            if button.is_visible() and "refresh" in button.inner_text().casefold():
                refresh_button = button
                break
        except Exception:
            pass

    if refresh_button is None:
        raise RuntimeError("Visible refresh button was not found")

    refresh_button.click(timeout=ACTION_TIMEOUT)
    log("Reload Availability clicked.")

    try:
        page.wait_for_function(
            """previous => [...document.querySelectorAll('.rz-timeslot')]
            .filter(e => { const r=e.getBoundingClientRect(), s=getComputedStyle(e);
                return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden'; })
            .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`).join('|') !== previous""",
            before,
            timeout=3000,
        )
    except Exception:
        pass


def check_for_open_slot(page) -> bool:
    slots = visible_available_slots(page)
    if not slots:
        log("No open slots found.")
        return False

    print()
    print("=" * 72)
    print("                    OPEN SLOT FOUND")
    print("=" * 72)
    for slot in slots:
        log(f"AVAILABLE: {describe_slot(slot)}")
    print("=" * 72)
    print("TEST MODE: No slot was selected and Reserve was NOT pressed.")
    print("The program is now ending.")
    print("=" * 72)
    return True


def main() -> None:
    print()
    print("=" * 72)
    print("          SASOL TRANSPORTERS - OPEN SLOT TEST MODE")
    print("=" * 72)
    print(f"Opening: {BASE_URL}")
    print("Login: manual")
    print("Navigation: manual")
    print("Action: REPORT OPEN SLOT ONLY")
    print("Reserve: DISABLED")
    print("=" * 72)
    print()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(ACTION_TIMEOUT)

            if page.url == "about:blank":
                log("Opening Sasol Transporters...")
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)

            print()
            print("Log in manually, then navigate to:")
            print("    Orders > Unscheduled Orders > Active Slots")
            print()
            print("Make sure the Active Slots grid is visible.")
            print("Type Y here when ready.")
            print()

            while input("Ready? [Y/N]: ").strip().casefold() not in {"y", "yes"}:
                print("Waiting for Y...")

            log("Checking for open slots...")

            while True:
                if check_for_open_slot(page):
                    break

                refresh(page)
                time.sleep(0.2)

                if check_for_open_slot(page):
                    break

        except KeyboardInterrupt:
            log("Test stopped with Ctrl+C.")
        finally:
            context.close()


if __name__ == "__main__":
    main()
