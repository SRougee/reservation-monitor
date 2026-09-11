"""Example configuration for reservation_monitor.py.

Copy these values into the SETTINGS section of reservation_monitor.py
or use this file as a reference while configuring your selectors.
"""

URL = "https://example.com/login"
LOGIN_TIME_SECONDS = 120

# CSS selector matching every repeated booking/availability block.
BLOCK_SELECTOR = ".booking-block"

# Optional text that must occur inside the desired block.
TARGET_TEXT = "10:30"

# Use the class that represents availability, if the site has one.
AVAILABLE_CLASS = "available"

# Alternatively detect a white background.
USE_WHITE_BACKGROUND = False
WHITE_RGB = "rgb(255, 255, 255)"

# Selector for the button that completes the reservation action.
RESERVED_BUTTON_SELECTOR = "button:has-text('Reserved')"

CHECK_INTERVAL = 1.0
PAGE_LOAD_TIMEOUT = 15_000
DEBUG = True
KEEP_BROWSER_OPEN_AFTER_SUCCESS = True
