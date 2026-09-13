"""Sasol Transporters reservation monitor GUI.

Two modes:
1. Watch Open Slots: checks every 3 minutes and reports available slots only.
2. Reserve Specific Slot: waits for a chosen date/hour, refreshing until it
   becomes Available or the user-defined attempt duration expires.

Login and navigation remain manual. Uses only visible website controls.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

BASE_URL = "https://www.sasoltransporters.com/sasol2024/"
URL = BASE_URL
SLOT_SELECTOR = '.rz-timeslot[title="Available"]'
ACTION_TIMEOUT = 3_000
PAGE_LOAD_TIMEOUT = 15_000
DOM_UPDATE_TIMEOUT = 3_000
PROFILE_DIR = Path(".browser-profile")


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class SasolMonitor:
    def __init__(self, gui):
        self.gui = gui
        self.stop_event = threading.Event()
        self.thread = None
        self.context = None
        self.page = None
        self.playwright = None

    def log(self, text):
        self.gui.after(0, self.gui.add_log, f"[{timestamp()}] {text}")

    def open_browser(self):
        self.log("Opening Sasol Transporters...")
        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=False,
            viewport={"width": 1400, "height": 900})
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(ACTION_TIMEOUT)
        if self.page.url == "about:blank":
            self.page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        self.log("Browser ready. Log in and navigate to Orders > Unscheduled Orders > Active Slots.")
        self.log("When the Active Slots grid is visible, click Start in the GUI.")

    def ensure_browser(self):
        if self.page is None or self.page.is_closed():
            self.open_browser()

    def visible_available(self):
        self.ensure_browser()
        locator = self.page.locator(SLOT_SELECTOR)
        result = []
        for i in range(locator.count()):
            slot = locator.nth(i)
            try:
                if slot.is_visible():
                    result.append(slot)
            except Exception:
                pass
        return result

    def describe_slot(self, slot):
        try:
            hour = (slot.inner_text() or "").strip()
            wrapper = slot.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' rz-timeslots-wrapper ')]").first
            date_text = (wrapper.locator(".rz-timeslots-date").inner_text() or "").strip()
            return f"{date_text} {hour}:00" if date_text else hour
        except Exception:
            return "unknown slot"

    def slot_signature(self):
        return self.page.locator(".rz-timeslot").evaluate_all("""
            elements => elements.filter(e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; })
            .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`).join('|')
        """)

    def refresh(self):
        before = self.slot_signature()
        buttons = self.page.locator("button")
        refresh = None
        for i in range(buttons.count()):
            b = buttons.nth(i)
            try:
                if b.is_visible() and "refresh" in b.inner_text().casefold():
                    refresh = b
                    break
            except Exception:
                pass
        if refresh is None:
            raise RuntimeError("Visible Refresh button was not found")
        refresh.click(timeout=ACTION_TIMEOUT)
        self.log("Refresh clicked.")
        try:
            self.page.wait_for_function("""
                previous => [...document.querySelectorAll('.rz-timeslot')]
                .filter(e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; })
                .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`).join('|') !== previous
            """, before, timeout=DOM_UPDATE_TIMEOUT)
        except PlaywrightTimeoutError:
            pass

    def reserve_slot(self, target_date, target_hour):
        slots = self.visible_available()
        target = target_date.strftime("%Y-%m-%d")
        for slot in slots:
            try:
                wrapper = slot.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' rz-timeslots-wrapper ')]").first
                date_text = (wrapper.locator(".rz-timeslots-date").inner_text() or "").strip()
                hour_text = (slot.inner_text() or "").strip()
                if target in date_text and hour_text == str(target_hour):
                    self.log(f"TARGET OPEN: {date_text} {hour_text}:00")
                    slot.click(timeout=ACTION_TIMEOUT)
                    self.log("Target slot selected. Pressing Reserve...")
                    buttons = self.page.locator("button")
                    reserve = None
                    for i in range(buttons.count()):
                        b = buttons.nth(i)
                        try:
                            if b.is_visible() and "reserve" in b.inner_text().casefold():
                                reserve = b
                                break
                        except Exception:
                            pass
                    if reserve is None:
                        raise RuntimeError("Visible Reserve button was not found")
                    reserve.click(timeout=ACTION_TIMEOUT)
                    self.log("Reserve clicked. Checking website response...")
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        dialogs = self.page.locator(".rz-dialog[role='dialog']")
                        for i in range(dialogs.count()):
                            d = dialogs.nth(i)
                            try:
                                if d.is_visible():
                                    text = (d.inner_text() or "").strip()
                                    self.log(f"Website response: {text}")
                                    if any(x in text.casefold() for x in ("no longer available", "error", "failed", "not available")):
                                        return False
                                    return True
                            except Exception:
                                pass
                        time.sleep(0.05)
                    self.log("No explicit confirmation was visible; stopping reservation attempt for safety.")
                    return False
            except Exception as exc:
                self.log(f"Target check error: {exc}")
        return False

    def watch_worker(self):
        self.log("WATCH MODE started — checks every 3 minutes.")
        while not self.stop_event.is_set():
            try:
                slots = self.visible_available()
                if slots:
                    self.log(f"OPEN SLOTS FOUND: {len(slots)}")
                    for slot in slots:
                        self.log(f"  AVAILABLE: {self.describe_slot(slot)}")
                else:
                    self.log("No open slots currently visible.")
                if self.stop_event.wait(180): break
                self.refresh()
            except Exception as exc:
                self.log(f"Watch error: {exc}")
                if self.stop_event.wait(1): break
        self.log("WATCH MODE stopped.")

    def reserve_worker(self, target_date, target_hour, duration_minutes):
        self.log(f"RESERVATION MODE started for {target_date:%Y-%m-%d} cell/hour {target_hour}.")
        deadline = datetime.now() + timedelta(minutes=duration_minutes)
        while not self.stop_event.is_set() and datetime.now() <= deadline:
            try:
                if self.reserve_slot(target_date, target_hour):
                    self.log("RESERVATION COMPLETED. Program stopped.")
                    return
                remaining = max(0, int((deadline - datetime.now()).total_seconds()))
                self.log(f"Target not available. Refreshing. Time remaining: {remaining}s")
                self.refresh()
            except Exception as exc:
                self.log(f"Reservation check error: {exc}")
                if self.stop_event.wait(1): return
        self.log("RESERVATION TIME LIMIT REACHED — no reservation made.")

    def start_watch(self):
        self.start(self.watch_worker)

    def start_reservation(self, target_date, target_hour, duration):
        self.start(lambda: self.reserve_worker(target_date, target_hour, duration))

    def start(self, worker):
        if self.thread and self.thread.is_alive():
            self.log("A monitor is already running.")
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        self.gui.set_running(True)

    def stop(self):
        self.stop_event.set()
        self.gui.set_running(False)
        self.log("Stop requested.")

    def close(self):
        self.stop_event.set()
        try:
            if self.context: self.context.close()
        except Exception: pass
        try:
            if self.playwright: self.playwright.stop()
        except Exception: pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sasol Transporters Slot Monitor")
        self.geometry("760x650")
        self.minsize(700, 600)
        self.monitor = SasolMonitor(self)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        threading.Thread(target=self.monitor.open_browser, daemon=True).start()

    def build_ui(self):
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="SASOL TRANSPORTERS", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Slot Monitor", font=("Segoe UI", 12)).pack(anchor="w", pady=(0, 15))

        modes = ttk.LabelFrame(outer, text="1. Watch Open Slots", padding=12)
        modes.pack(fill="x", pady=(0, 12))
        ttk.Label(modes, text="Checks the Active Slots grid every 3 minutes and reports open slots. It never reserves.").pack(anchor="w")
        self.watch_btn = ttk.Button(modes, text="START WATCHING", command=self.monitor.start_watch)
        self.watch_btn.pack(anchor="w", pady=(10, 0))

        reserve = ttk.LabelFrame(outer, text="2. Reserve a Specific Slot", padding=12)
        reserve.pack(fill="x", pady=(0, 12))
        row = ttk.Frame(reserve); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Date (YYYY-MM-DD):").pack(side="left")
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(row, textvariable=self.date_var, width=16).pack(side="left", padx=(8, 20))
        ttk.Label(row, text="Cell / Hour:").pack(side="left")
        self.hour_var = tk.StringVar(value="10")
        ttk.Entry(row, textvariable=self.hour_var, width=7).pack(side="left", padx=8)
        row2 = ttk.Frame(reserve); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="How long to try (minutes):").pack(side="left")
        self.duration_var = tk.StringVar(value="60")
        ttk.Entry(row2, textvariable=self.duration_var, width=10).pack(side="left", padx=8)
        self.reserve_btn = ttk.Button(reserve, text="START RESERVATION", command=self.start_reservation)
        self.reserve_btn.pack(anchor="w", pady=(10, 0))
        ttk.Label(reserve, text="The program refreshes and checks only this date/cell until reserved or the time limit expires.").pack(anchor="w", pady=(8, 0))

        control = ttk.Frame(outer); control.pack(fill="x", pady=(0, 10))
        self.stop_btn = ttk.Button(control, text="STOP", command=self.monitor.stop)
        self.stop_btn.pack(side="left")
        self.status_var = tk.StringVar(value="Opening browser...")
        ttk.Label(control, textvariable=self.status_var).pack(side="left", padx=15)

        log_frame = ttk.LabelFrame(outer, text="Activity Log", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=15, wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

    def add_log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_running(self, running):
        self.status_var.set("RUNNING" if running else "READY / STOPPED")
        state = "disabled" if running else "normal"
        self.watch_btn.configure(state=state)
        self.reserve_btn.configure(state=state)

    def start_reservation(self):
        try:
            target_date = datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d").date()
            hour = int(self.hour_var.get().strip())
            duration = float(self.duration_var.get().strip())
            if not 0 <= hour <= 23: raise ValueError("Cell/hour must be between 0 and 23.")
            if duration <= 0: raise ValueError("Duration must be greater than 0 minutes.")
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        self.monitor.start_reservation(target_date, hour, duration)

    def on_close(self):
        self.monitor.close()
        self.destroy()


if __name__ == "__main__":
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    App().mainloop()
