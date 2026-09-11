# DOM Reservation Monitor

A small Python + Playwright utility for monitoring a webpage that contains repeated booking/availability blocks and acting when a matching block becomes available.

The monitor is **DOM-based**. It does not use screenshots, OCR, image recognition, or screen coordinates.

> **Important:** This project does not solve or bypass CAPTCHA. Login and CAPTCHA completion are performed manually in the visible browser.

## Features

- Opens a visible Chromium browser.
- Gives you a configurable period to log in and complete CAPTCHA manually.
- Allows you to navigate to the exact page before monitoring starts.
- Uses Playwright DOM selectors to inspect repeated blocks.
- Can identify availability using a CSS class and/or a white background.
- Can filter for a specific target text within a block.
- Refreshes the page on an approximately one-second cycle by default.
- Measures refresh and scan times in the console.
- Clicks the matching block and then the configured **Reserved** button.
- Stops after the reservation action succeeds or if the expected Reserved button cannot be found.
- Uses a persistent local browser profile so session cookies may be retained between runs when permitted by the website.
- Keeps browser/session data out of Git via `.gitignore`.

## Requirements

- Windows, macOS, or Linux
- Python 3.9+
- Internet access
- A website that permits the relevant automated browser interaction

## Installation

Clone the repository:

```bash
git clone https://github.com/SRougee/reservation-monitor.git
cd reservation-monitor
```

Create a virtual environment (recommended):

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

## Configuration

Open `reservation_monitor.py` and edit the **SETTINGS** section near the top.

### Website URL

```python
URL = "https://example.com/login"
```

This is the page opened when the program starts. It can be a login page.

### Login period

```python
LOGIN_TIME_SECONDS = 120
```

The browser remains available for this period so you can log in, complete CAPTCHA, and navigate to the desired page.

### Block selector

This is the most important setting:

```python
BLOCK_SELECTOR = ".booking-block"
```

It must match the repeated blocks that the program needs to inspect.

For example, if the page contains:

```html
<div class="booking-block">...</div>
<div class="booking-block">...</div>
<div class="booking-block">...</div>
```

use:

```python
BLOCK_SELECTOR = ".booking-block"
```

### Target text

If only one particular block should be selected, you can require text to appear inside it:

```python
TARGET_TEXT = "10:30"
```

Leave it empty if any available block is acceptable:

```python
TARGET_TEXT = ""
```

### Availability class

If the website changes a class when a block becomes available:

```html
<div class="booking-block unavailable">...</div>
```

and later:

```html
<div class="booking-block available">...</div>
```

configure:

```python
BLOCK_SELECTOR = ".booking-block"
AVAILABLE_CLASS = "available"
```

### White background

If the site's availability state is represented by a white background rather than a useful class, enable:

```python
USE_WHITE_BACKGROUND = True
```

The default expected browser colour is:

```python
WHITE_RGB = "rgb(255, 255, 255)"
```

The program checks the computed CSS background colour through the DOM.

### Reserved button

Configure the selector for the button that appears after selecting the block:

```python
RESERVED_BUTTON_SELECTOR = "button:has-text('Reserved')"
```

Other examples:

```python
RESERVED_BUTTON_SELECTOR = "#reserveButton"
```

or:

```python
RESERVED_BUTTON_SELECTOR = "[data-action='reserve']"
```

## Running the program

```bash
python reservation_monitor.py
```

The program will:

1. Open Chromium.
2. Open the configured URL.
3. Give you the configured login period.
4. Allow you to log in and complete CAPTCHA manually.
5. Allow you to navigate to the required page.
6. Ask you to press **Enter**.
7. Begin inspecting the configured blocks.
8. Refresh approximately once per second.
9. Detect a matching available block.
10. Click the block.
11. Click the Reserved button.
12. Stop.

## The one-second cycle

`CHECK_INTERVAL` controls the target duration for a complete cycle:

```python
CHECK_INTERVAL = 1.0
```

The program does not simply sleep for one second after every operation. It measures the work already performed and only waits for the remainder of the target interval.

For example, if a scan takes 0.2 seconds, it waits approximately 0.8 seconds before the next refresh.

The actual rate is limited by the website. If a complete page reload takes 1.5 seconds, a true one-second refresh cycle is physically impossible using full page reloads.

## Finding selectors

Use the browser's developer tools:

1. Open the target page.
2. Right-click one of the blocks.
3. Select **Inspect**.
4. Examine its HTML.
5. Look for a stable class, ID, `data-*` attribute, or other selector.
6. Compare the HTML/CSS of an unavailable block with one that is available.

Prefer stable attributes/classes over generated CSS paths or screen coordinates.

### Example

Suppose inspection shows:

```html
<div class="slot" data-status="available">
    10:30
</div>
```

A useful configuration might be:

```python
BLOCK_SELECTOR = ".slot"
AVAILABLE_CLASS = ""
TARGET_TEXT = "10:30"
```

If the status is instead represented by a class:

```html
<div class="slot available">10:30</div>
```

use:

```python
BLOCK_SELECTOR = ".slot"
AVAILABLE_CLASS = "available"
TARGET_TEXT = "10:30"
```

## Persistent browser profile

The program stores Playwright's browser profile in:

```text
.browser-profile/
```

This can retain cookies and login/session information between runs when the website allows it.

**Do not commit this directory.** It is already excluded by `.gitignore`.

If you need to start with a completely clean browser session, stop the program and delete `.browser-profile/`.

## Debugging

Keep this enabled while configuring the program:

```python
DEBUG = True
```

The console will report information such as:

```text
[17:30:01.123] Cycle 1: checking page...
[17:30:01.140] Found 40 blocks
[17:30:01.150] No matching available block.
[17:30:01.151] Cycle completed in 0.028 seconds
[17:30:02.001] Refreshing...
[17:30:02.412] Refresh completed in 0.411 seconds
```

This is useful for determining whether the bottleneck is DOM inspection or page reload time.

## Safety and responsible use

Use this software only on websites and accounts where you are authorized to automate the relevant interaction. Check the website's terms, booking rules, and any applicable rate limits before running a high-frequency monitor.

The program intentionally does not attempt to defeat CAPTCHA or other access controls.

## Troubleshooting

### `Found 0 blocks`

Your `BLOCK_SELECTOR` probably does not match the actual DOM. Inspect one block and update the selector.

### Blocks are found but availability is never detected

Compare an unavailable and available block in Developer Tools. The site may use a different class, attribute, inline style, or computed style.

### The block is detected but the wrong block is selected

Set `TARGET_TEXT` to text unique to the required block, or configure a more precise selector/state check.

### Reserved button is not found

Inspect the Reserved button and replace `RESERVED_BUTTON_SELECTOR` with a stable selector.

### The page reloads too slowly

The site may simply take longer than one second to reload. In that case, consider whether the page updates its availability through JavaScript/API calls; a future version could monitor those DOM updates without performing a full reload each time.

## Licence

This project is released under the MIT License. See `LICENSE`.
