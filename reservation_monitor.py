"""Sasol Transporters reservation monitor GUI."""
from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

BASE_URL = "https://www.sasoltransporters.com/sasol2024/"
SLOT_SELECTOR = '.rz-timeslot[title="Available"]'
ACTION_TIMEOUT = 3_000
PAGE_LOAD_TIMEOUT = 15_000
DOM_UPDATE_TIMEOUT = 3_000
RESERVATION_REFRESH_DELAY = 0.75
PROFILE_DIR = Path(".browser-profile")


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class SasolMonitor:
    """Own all Playwright objects from one dedicated thread.

    Tkinter stays on the GUI thread. Commands are queued to this worker, so
    Playwright is never called concurrently from multiple Python threads.
    """

    def __init__(self, gui):
        self.gui = gui
        self.commands: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.ready = threading.Event()
        self.closing = False
        self.worker.start()

    def log(self, text):
        if not self.closing:
            self.gui.after(0, self.gui.add_log, f"[{timestamp()}] {text}")

    def _run(self):
        playwright = None
        context = None
        page = None
        try:
            self.log("Opening Sasol Transporters...")
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR), headless=False,
                viewport={"width": 1400, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(ACTION_TIMEOUT)
            if page.url == "about:blank":
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            self.ready.set()
            self.log("Browser ready. Log in and navigate to Orders > Unscheduled Orders > Active Slots.")
            self.log("When the Active Slots grid is visible, click Start in the GUI.")

            while not self.closing:
                try:
                    command = self.commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                if command[0] == "watch":
                    self._watch(page)
                elif command[0] == "reserve":
                    self._reserve(page, *command[1:])
                elif command[0] == "stop":
                    self.stop_event.set()
        except Exception as exc:
            self.log(f"Browser error: {exc}")
        finally:
            self.ready.set()
            try:
                if context:
                    context.close()
            except Exception:
                pass
            try:
                if playwright:
                    playwright.stop()
            except Exception:
                pass

    def _visible_available(self, page):
        locator = page.locator(SLOT_SELECTOR)
        result = []
        for i in range(locator.count()):
            slot = locator.nth(i)
            try:
                if slot.is_visible():
                    result.append(slot)
            except Exception:
                pass
        return result

    def _describe_slot(self, slot):
        try:
            hour = (slot.inner_text() or "").strip()
            wrapper = slot.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' rz-timeslots-wrapper ')]").first
            date_text = (wrapper.locator(".rz-timeslots-date").inner_text() or "").strip()
            return f"{date_text} {hour}:00" if date_text else hour
        except Exception:
            return "unknown slot"

    def _slot_signature(self, page):
        return page.locator(".rz-timeslot").evaluate_all("""
            elements => elements.filter(e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; })
            .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`).join('|')
        """)

    def _refresh(self, page, wait_for_change=True):
        before = self._slot_signature(page) if wait_for_change else None
        buttons = page.locator("button")
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
        if not wait_for_change:
            self._wait(RESERVATION_REFRESH_DELAY)
            return
        try:
            page.wait_for_function("""
                previous => [...document.querySelectorAll('.rz-timeslot')]
                .filter(e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; })
                .map(e => `${e.title}:${e.className}:${e.textContent.trim()}`).join('|') !== previous
            """, before, timeout=DOM_UPDATE_TIMEOUT)
        except PlaywrightTimeoutError:
            pass

    def _wait(self, seconds):
        return self.stop_event.wait(seconds)

    def _watch(self, page):
        self.stop_event.clear()
        self.log("WATCH MODE started — checks every 3 minutes.")
        while not self.stop_event.is_set() and not self.closing:
            try:
                slots = self._visible_available(page)
                if slots:
                    self.log(f"OPEN SLOTS FOUND: {len(slots)}")
                    for slot in slots:
                        self.log(f"  AVAILABLE: {self._describe_slot(slot)}")
                else:
                    self.log("No open slots currently visible.")
                if self._wait(180):
                    break
                self._refresh(page)
            except Exception as exc:
                self.log(f"Watch error: {exc}")
                if self._wait(1):
                    break
        self.log("WATCH MODE stopped.")
        self.gui.after(0, self.gui.set_running, False)

    def _target_slot(self, page, target_date, target_hour):
        """Return only the requested date/hour cell, if it is available."""
        target = target_date.strftime("%Y-%m-%d")
        wrappers = page.locator(".rz-timeslots-wrapper")
        for i in range(wrappers.count()):
            wrapper = wrappers.nth(i)
            try:
                if not wrapper.is_visible():
                    continue
                date_text = (wrapper.locator(".rz-timeslots-date").inner_text() or "").strip()
                if target not in date_text:
                    continue
                cells = wrapper.locator(".rz-timeslot")
                for j in range(cells.count()):
                    cell = cells.nth(j)
                    if not cell.is_visible():
                        continue
                    hour_text = (cell.inner_text() or "").strip()
                    if hour_text == str(target_hour) and cell.get_attribute("title") == "Available":
                        return cell, date_text
                return None, date_text
            except Exception:
                continue
        return None, None

    def _reserve_slot(self, page, target_date, target_hour):
        """Attempt only the exact requested date/hour once."""
        slot, date_text = self._target_slot(page, target_date, target_hour)
        if slot is None:
            return False

        self.log(f"TARGET OPEN: {date_text} {target_hour}:00")
        slot.click(timeout=ACTION_TIMEOUT)

        # Find the normal visible Reserve control immediately after selecting
        # the target. Do not scan or interact with any other slot.
        reserve = page.locator("button:has-text('Reserve')")
        visible_reserve = None
        for i in range(reserve.count()):
            button = reserve.nth(i)
            try:
                if button.is_visible():
                    visible_reserve = button
                    break
            except Exception:
                pass
        if visible_reserve is None:
            raise RuntimeError("Visible Reserve button was not found")

        self.log("Target slot selected. Pressing Reserve...")
        visible_reserve.click(timeout=ACTION_TIMEOUT)
        self.log("Reserve clicked. Checking website response...")

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            dialogs = page.locator(".rz-dialog[role='dialog']")
            for i in range(dialogs.count()):
                dialog = dialogs.nth(i)
                try:
                    if not dialog.is_visible():
                        continue
                    text = (dialog.inner_text() or "").strip()
                    if not text:
                        continue
                    self.log(f"Website response: {text}")
                    lower = text.casefold()
                    bad = ("no longer available", "error", "failed", "not available")
                    if any(x in lower for x in bad):
                        # Dismiss the site's error immediately so the same
                        # target can be retried after the next refresh.
                        ok_buttons = dialog.locator("button")
                        for j in range(ok_buttons.count()):
                            ok = ok_buttons.nth(j)
                            try:
                                if ok.is_visible() and (ok.inner_text() or "").strip().casefold() == "ok":
                                    ok.click(timeout=ACTION_TIMEOUT)
                                    self.log("Sasol error dismissed. Target will be retried.")
                                    break
                            except Exception:
                                pass
                        return False
                    return True
                except Exception:
                    pass
            time.sleep(0.05)

        self.log("No explicit confirmation was visible; stopping reservation attempt for safety.")
        return False

    def _reserve(self, page, target_date, target_hour, duration_minutes):
        self.stop_event.clear()
        self.log(f"RESERVATION MODE started for {target_date:%Y-%m-%d} cell/hour {target_hour}.")
        deadline = datetime.now() + timedelta(minutes=duration_minutes)
        first_check = True
        while not self.stop_event.is_set() and not self.closing and datetime.now() <= deadline:
            try:
                if self._reserve_slot(page, target_date, target_hour):
                    self.log("RESERVATION COMPLETED. Program stopped.")
                    self.gui.after(0, self.gui.set_running, False)
                    return
                remaining = max(0, int((deadline - datetime.now()).total_seconds()))
                if remaining <= 0:
                    break
                if first_check:
                    self.log(f"Target unavailable. Refreshing and retrying. Time remaining: {remaining}s")
                    first_check = False
                else:
                    self.log(f"Target unavailable. Refreshing and retrying. Time remaining: {remaining}s")
                self._refresh(page, wait_for_change=False)
            except Exception as exc:
                self.log(f"Reservation check error: {exc}")
                if self._wait(1):
                    break
        if not self.stop_event.is_set():
            self.log("RESERVATION TIME LIMIT REACHED — no reservation made.")
        else:
            self.log("RESERVATION MODE stopped.")
        self.gui.after(0, self.gui.set_running, False)

    def start_watch(self):
        if not self.ready.is_set() or self.closing:
            self.log("Browser is not ready yet. Please wait a moment and try again.")
            return
        self.commands.put(("watch",))
        self.gui.set_running(True)

    def start_reservation(self, target_date, target_hour, duration):
        if not self.ready.is_set() or self.closing:
            self.log("Browser is not ready yet. Please wait a moment and try again.")
            return
        self.commands.put(("reserve", target_date, target_hour, duration))
        self.gui.set_running(True)

    def stop(self):
        self.stop_event.set()
        self.commands.put(("stop",))
        self.gui.set_running(False)
        self.log("Stop requested. Browser will remain open.")

    def close(self):
        self.closing = True
        self.stop_event.set()
        try:
            self.commands.put(("stop",))
        except Exception:
            pass
        if self.worker.is_alive() and self.worker is not threading.current_thread():
            self.worker.join(timeout=6)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sasol Transporters Slot Monitor")
        self.geometry("760x650")
        self.minsize(700, 600)
        self.monitor = SasolMonitor(self)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()

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
        self.exit_btn = ttk.Button(control, text="EXIT", command=self.on_close)
        self.exit_btn.pack(side="left", padx=(8, 0))
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
        if self.monitor.closing:
            return
        self.status_var.set("RUNNING" if running else "READY / STOPPED")
        state = "disabled" if running else "normal"
        self.watch_btn.configure(state=state)
        self.reserve_btn.configure(state=state)

    def start_reservation(self):
        try:
            target_date = datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d").date()
            hour = int(self.hour_var.get().strip())
            duration = float(self.duration_var.get().strip())
            if not 0 <= hour <= 23:
                raise ValueError("Cell/hour must be between 0 and 23.")
            if duration <= 0:
                raise ValueError("Duration must be greater than 0 minutes.")
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        self.monitor.start_reservation(target_date, hour, duration)

    def on_close(self):
        if self.monitor.closing:
            return
        if messagebox.askyesno("Exit", "Are you sure you want to exit?\n\nThe monitor will stop and the Sasol browser will be closed safely."):
            self.monitor.close()
            self.destroy()


if __name__ == "__main__":
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    App().mainloop()
