# DOM Reservation Monitor

A configurable Python + Playwright utility for monitoring a webpage containing repeated availability/booking blocks and acting when a matching block becomes available.

The monitor is **DOM-based**. It does not use screenshots, OCR, image recognition, or screen coordinates.

> **Important:** This project does not solve or bypass CAPTCHA. Login and CAPTCHA completion are performed manually in the visible browser.

## Test environment

This repository now includes a complete simulated reservation website for safely testing the monitor.

The test environment contains:

- Real dummy login/session handling.
- Hardcoded test passwords because this is a simulation environment.
- Landing page and dummy pages.
- A reservation page with **40 cells: 8 columns × 5 rows**.
- 8 permanently unavailable red cells.
- Grey unavailable cells.
- White available cells.
- Random opening of 1-4 grey cells every 30 seconds.
- White cells remain available until reserved.
- Multiple-cell selection.
- A top-right **Reserve Selected** button.
- A **Reload Availability** button that refreshes only the reservation grid rather than the whole page.
- Shared state across multiple browser sessions through Cloudflare D1.
- Reservation history recording cell, user, opening time, reservation time and open duration.
- An admin page with a live log and manual test controls.

### Test-site structure

```text
test-site/
├── public/              <-- WEBSITE FILES DEPLOYED AS STATIC ASSETS
│   ├── index.html
│   ├── landing.html
│   ├── dummy.html
│   ├── reservation.html
│   ├── admin.html
│   ├── app.js
│   └── styles.css
├── worker/
│   └── index.js         <-- CLOUDFLARE WORKER API
├── schema.sql           <-- D1 DATABASE SCHEMA
├── wrangler.toml        <-- CLOUDFLARE FILE-LOCATION CONFIGURATION
├── package.json
├── .assetsignore
├── DEPLOY.md
└── README.md
```

### Important Cloudflare file-location detail

If you are referring to Cloudflare's deployment/build tooling as the crawler, the important setting is the Wrangler **`assets.directory`** configuration. Current Cloudflare Workers Static Assets uses this setting to tell Wrangler exactly where the browser-facing files are located. citeturn0search0turn0search2

For this repository it is explicitly:

```toml
[assets]
directory = "./public"
binding = "ASSETS"
run_worker_first = ["/api/*"]
```

Because `wrangler.toml` is inside `test-site/`, the actual website files are:

```text
reservation-monitor/test-site/public/
```

The Worker is:

```text
reservation-monitor/test-site/worker/index.js
```

The D1 schema is:

```text
reservation-monitor/test-site/schema.sql
```

**Do not configure Cloudflare to use the repository root as the website directory.**

Cloudflare's current Workers Static Assets model can deploy the Worker and static assets together, with API paths sent through the Worker and normal website files served from the configured assets directory. citeturn0search2

## Test accounts

These passwords are deliberately hardcoded and un-hashed because this is a disposable simulation:

| Username | Password | Role |
|---|---|---|
| `testuser` | `test123` | Test user |
| `admin` | `admin123` | Administrator |
| `monitor` | `monitor123` | Playwright monitor |

**Do not reuse these credentials or this authentication design in production.**

## Three-browser test setup

The intended test configuration is:

### Browser 1 — test user

Log in as `testuser` and open the reservation page.

Use it to select and reserve cells manually.

### Browser 2 — administrator

Log in as `admin` and open the admin page.

This browser shows the reservation log and allows controlled testing:

- Open random cells
- Open a specific cell
- Close a specific cell
- Reset the grid
- Clear the reservation log

### Browser 3 — monitor

Run `reservation_monitor.py` with the test-site URL and log in as `monitor`.

This is the browser that exercises the actual DOM-monitoring code.

Because the state is stored in D1, all three sessions see the same reservation state.

## Cloudflare deployment

The recommended free-first architecture is:

```text
Browser
   │
   ▼
Cloudflare Worker + Static Assets
   │
   ├── /                 static website
   ├── /landing.html     static page
   ├── /dummy.html       static page
   ├── /reservation.html static reservation page
   ├── /admin.html       static admin page
   │
   └── /api/*            Worker API
                         │
                         ▼
                    Cloudflare D1
```

D1 is bound to the Worker using the `DB` binding in `wrangler.toml`. Cloudflare documents D1 bindings through the `[[d1_databases]]` configuration. citeturn0search1turn0search10

See [`test-site/DEPLOY.md`](test-site/DEPLOY.md) for the complete deployment sequence.

### Basic deployment

From the `test-site` directory:

```bash
npm install
npx wrangler login
npx wrangler d1 create reservation-monitor-test
```

Put the returned database ID into `wrangler.toml`, replacing `<YOUR-D1-DATABASE-ID>`.

Then:

```bash
npx wrangler d1 execute reservation-monitor-test --remote --file=./schema.sql
npx wrangler deploy
```

Cloudflare's current documentation recommends Workers Static Assets for full-stack applications rather than the older Workers Sites approach. citeturn0search5

## Monitor configuration for the simulator

Once the test site has a URL, the monitor can be configured approximately as follows:

```python
URL = "https://YOUR-TEST-SITE.workers.dev/"
BLOCK_SELECTOR = ".booking-block"
AVAILABLE_CLASS = "available"
USE_WHITE_BACKGROUND = True
WHITE_RGB = "rgb(255, 255, 255)"
RESERVED_BUTTON_SELECTOR = "#reserveButton"
```

The exact configuration can be refined after inspecting the deployed DOM.

## Monitor features

- Opens a visible Chromium browser.
- Gives you a configurable period to log in manually.
- Allows navigation to the exact page before monitoring starts.
- Uses Playwright DOM selectors.
- Can identify availability using a CSS class and/or white background.
- Can filter for specific text within a block.
- Measures scan and refresh times.
- Clicks a matching block and then the configured Reserved button.
- Uses a persistent browser profile for permitted session retention.
- Keeps browser/session data out of Git via `.gitignore`.

## Installation

```bash
git clone https://github.com/SRougee/reservation-monitor.git
cd reservation-monitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

On macOS/Linux, activate with:

```bash
source .venv/bin/activate
```

## Running the monitor

```bash
python reservation_monitor.py
```

The monitor opens Chromium, gives you time to log in, and then asks you to press Enter before monitoring begins.

## One-second monitoring cycle

`CHECK_INTERVAL = 1.0` targets approximately one complete monitoring cycle per second, but the actual speed is limited by the website's response time.

The test site deliberately uses a **partial availability reload** for its human-facing Reload button, while the monitor can continue using its normal page-reload behaviour. This lets us compare both approaches.

## Finding selectors

Use browser Developer Tools to inspect a block and identify stable classes, IDs or `data-*` attributes. Avoid screen coordinates and generated CSS paths.

For the simulator, the primary selector is:

```css
.booking-block
```

and available blocks receive:

```css
.available
```

## Persistent browser profile

Playwright stores its persistent session under:

```text
.browser-profile/
```

This is excluded by `.gitignore` because it may contain cookies/session information.

## Safety

Use the monitor only on websites and accounts where you are authorized to automate the relevant interaction. The program intentionally does not attempt to solve or bypass CAPTCHA.

## Licence

MIT License. See `LICENSE`.
