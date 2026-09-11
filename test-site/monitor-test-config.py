"""Reference settings for testing reservation_monitor.py against the Cloudflare simulator.

Replace TEST_SITE_URL with the URL returned by `wrangler deploy`.
The monitor still performs login manually in its visible browser.
"""

URL = "https://YOUR-TEST-SITE.workers.dev/"
LOGIN_TIME_SECONDS = 120
BLOCK_SELECTOR = ".booking-block"
TARGET_TEXT = ""
AVAILABLE_CLASS = "available"
USE_WHITE_BACKGROUND = True
WHITE_RGB = "rgb(255, 255, 255)"
RESERVED_BUTTON_SELECTOR = "#reserveButton"
CHECK_INTERVAL = 1.0
PAGE_LOAD_TIMEOUT = 15_000
DEBUG = True
KEEP_BROWSER_OPEN_AFTER_SUCCESS = True
