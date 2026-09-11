# DOM Reservation Monitor

A Python + Playwright project for building a **fast, browser-based reservation monitor** that watches a reservation webpage, detects when cells become available, selects all matching availability, and submits the reservation as quickly as realistically possible.

The project has two purposes:

1. **Train and test safely** against our own reservation simulator.
2. **Build a reusable monitoring engine** that can later be adapted to an authorized practical-test website without assuming access to that website's server, database, source code, or private APIs.

The central design principle is:

> **Use only information and actions that a normal logged-in browser can realistically access. React as quickly as possible to the website's visible changes, without giving the monitor privileged server access.**

The monitor uses Playwright and the browser DOM. It does not use screenshots, OCR, image recognition, screen coordinates, Cloudflare/D1 access, or the simulator's Admin Log.

> **Important:** This project does not solve or bypass CAPTCHA. Login and CAPTCHA completion are performed manually in the visible browser. Use automation only where you are authorized to do so.

---

# 1. Project mission

The practical problem we are solving is simple:

**A reservation website may have a limited number of cells/slots that become available. We want the monitor to notice availability and act immediately, while behaving like a normal browser user rather than relying on privileged access to the site's backend.**

Speed matters, but speed must come from removing unnecessary work rather than from pretending we can control the server.

## Our optimisation priorities

1. Keep the browser already logged in and on the reservation page.
2. Use the website's normal **Reload Availability** control when the site requires it.
3. Never reload the entire page unless the real site actually requires it.
4. Do not use arbitrary sleeps between detection, selection and reservation.
5. Detect the browser-visible DOM change caused by a refresh as soon as possible.
6. Find **all** currently available matching cells together.
7. Select those cells in one browser-side operation rather than one Playwright round-trip per cell.
8. Submit all selected cells together where the website supports multi-selection.
9. Confirm the actual reservation result rather than assuming a button click succeeded.
10. Recover from transient browser errors and continue until Ctrl+C.

The simulator is intentionally designed to help us test these principles before the practical test.

---

# 2. What we assume about the real website

We do **not** assume that we will have access to the real website's server.

When the practical test arrives, we expect to have something closer to:

```text
A normal browser
      +
A legitimate login
      +
The reservation webpage
```

Therefore, the monitor is deliberately designed around browser-visible information.

We may be able to observe things such as:

- HTML/DOM elements
- CSS classes and attributes
- JavaScript-driven DOM changes
- visible buttons and controls
- browser-visible network behaviour, where appropriate and authorized
- normal login/session state

We will **not** design the real-site version around assumptions such as:

- access to the site's database
- Cloudflare credentials
- backend source code
- private API credentials
- administrator pages
- hidden server-side state

If the real website uses WebSockets, Server-Sent Events, AJAX/fetch, or another browser-visible mechanism, we can investigate that when we are actually given the site. We will use the mechanism that is legitimately exposed to the browser rather than guessing in advance.

---

# 3. Current monitoring strategy

The current simulator represents a website where the user must press **Reload Availability** to request the latest availability.

The monitor therefore follows this pattern:

```text
Browser stays on reservation page
              │
              ▼
      Check visible cells
              │
       Available cells?
          │        │
         YES       NO
          │        │
          ▼        ▼
      Select all  Press normal
      available   Reload Availability
          │        │
          │        ▼
          │   Wait for DOM change
          │        │
          │        ▼
          │   Check immediately
          │
          ▼
    Reserve Selected
          │
          ▼
    Verify confirmation
          │
          ▼
        Repeat
```

The important optimisation is that **there is no artificial polling delay between pressing Reload and checking the resulting DOM**. Playwright waits for the browser-visible change instead.

The monitor also does not click cells one at a time from Python. It uses one browser-side operation to identify and select all available matching cells.

---

# 4. Test environment

This repository contains a complete simulated reservation website for safe development and testing.

The simulator contains:

- Dummy login/session handling.
- Three test accounts.
- Landing and dummy pages.
- A reservation page with **40 cells: 8 columns × 5 rows**.
- 8 permanently unavailable red cells.
- Grey unavailable cells.
- White/available cells.
- Server-side availability generation every 30 seconds.
- A human-facing **Reload Availability** button.
- Multiple-cell selection.
- A **Reserve Selected** button.
- Shared state across browser sessions through Cloudflare D1.
- Reservation history including cell, user, opening time, reservation time and open duration.
- An administrator page with a live reservation log and manual test controls.

The simulator is intentionally separate from the monitor. The monitor is treated as an ordinary browser client.

---

# 5. Test accounts

These credentials are deliberately simple because this is a disposable simulation environment.

| Username | Password | Role |
|---|---|---|
| `testuser` | `test123` | Test user |
| `admin` | `admin123` | Administrator |
| `monitor` | `monitor123` | Playwright monitor |

**Do not reuse these credentials or this authentication design in production.**

---

# 6. Three-browser test setup

The recommended simulator test uses three separate browser sessions.

## Browser 1 — Test user

Log in as:

```text
Username: testuser
Password: test123
```

Open the Reservations page.

This browser is useful for manually reserving cells and testing contention.

## Browser 2 — Administrator

Log in as:

```text
Username: admin
Password: admin123
```

Open the Admin page.

The administrator can:

- Open random cells
- Open a specific cell
- Close a specific cell
- Reset the grid
- Clear the reservation log
- View reservations

The monitor does **not** use this page.

## Browser 3 — Monitor

The Python program opens its own visible Chromium session.

Log in as:

```text
Username: monitor
Password: monitor123
```

Navigate to Reservations and start the monitor.

Because reservation state is stored in D1, all sessions see the same underlying test state.

---

# 7. Repository structure

```text
reservation-monitor/
│
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
├── reservation_monitor.py
├── config.example.py
│
└── test-site/
    ├── public/              <-- browser-facing website files
    │   ├── index.html
    │   ├── landing.html
    │   ├── dummy.html
    │   ├── reservation.html
    │   ├── admin.html
    │   ├── app.js
    │   └── styles.css
    │
    ├── worker/
    │   └── index.js         <-- Cloudflare Worker API
    │
    ├── schema.sql           <-- D1 database schema/seed
    ├── wrangler.toml        <-- Cloudflare configuration
    ├── package.json
    ├── .assetsignore
    ├── DEPLOY.md
    └── README.md
```

### Important file-location detail

Because `wrangler.toml` is inside `test-site/`, the browser-facing static files are in:

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

Do not configure the repository root as the static website directory.

---

# 8. Installation — from the beginning

This section assumes a fresh Windows computer and is intentionally written step-by-step.

## Step 1 — Install Python

Install a current Python 3 release from the official Python website.

During installation on Windows, make sure Python is available from the command line.

Verify it:

```powershell
py --version
```

You should see a Python version such as:

```text
Python 3.x.x
```

---

## Step 2 — Install Git

Install Git for Windows.

Verify:

```powershell
git --version
```

---

## Step 3 — Clone the project

Open PowerShell and run:

```powershell
git clone https://github.com/SRougee/reservation-monitor.git
```

Then enter the project:

```powershell
cd reservation-monitor
```

---

## Step 4 — Create a Python virtual environment

From the project root:

```powershell
py -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation because of its execution policy, you can either use Command Prompt or adjust your local PowerShell policy appropriately. Do not disable security controls globally just for this project.

After activation you should see something like:

```text
(.venv) PS C:\...\reservation-monitor>
```

---

## Step 5 — Install Python dependencies

Run:

```powershell
py -m pip install -r requirements.txt
```

The main dependency is Playwright.

---

## Step 6 — Install the Chromium browser used by Playwright

Run:

```powershell
py -m playwright install chromium
```

Verify Playwright:

```powershell
py -m playwright --version
```

---

# 9. Cloudflare test-site setup

The Python monitor does **not** require Cloudflare access. Cloudflare is only needed if you want to run our simulator.

The simulator uses:

```text
Cloudflare Workers
        +
Workers Static Assets
        +
Cloudflare D1
```

## Step 1 — Install Node.js

Install a current Node.js release if it is not already installed.

Verify:

```powershell
node --version
npm --version
```

## Step 2 — Enter the test site

From the repository root:

```powershell
cd test-site
```

## Step 3 — Install JavaScript dependencies

```powershell
npm install
```

## Step 4 — Log in to Cloudflare

```powershell
npx wrangler login
```

A browser window will open for Cloudflare authentication.

## Step 5 — Create the D1 database

```powershell
npx wrangler d1 create reservation-monitor-test
```

Cloudflare will return a database ID.

Put that ID into `wrangler.toml` under the `[[d1_databases]]` configuration.

## Step 6 — Create the database tables and test data

Run:

```powershell
npx wrangler d1 execute reservation-monitor-test --remote --file=./schema.sql
```

## Step 7 — Deploy the simulator

```powershell
npx wrangler deploy
```

Wrangler will provide the deployed `workers.dev` URL.

## Step 8 — Return to the project root

```powershell
cd ..
```

---

# 10. Running the monitor

From the repository root, with the Python virtual environment activated:

```powershell
py reservation_monitor.py
```

The monitor opens a visible Chromium window.

It will ask you to log in and navigate to the Reservations page manually.

When ready, type:

```text
Y
```

The monitor then runs continuously until:

```text
Ctrl+C
```

---

# 11. What the monitor does

The current monitor deliberately avoids privileged server access.

It uses:

- Playwright
- the visible browser
- the reservation page DOM
- the site's normal Reload Availability button
- the site's normal Reserve Selected button
- browser-visible reservation confirmation

It does **not** use:

- D1
- Cloudflare API credentials
- Worker source code
- the Admin Log
- direct database queries
- direct simulator API calls
- screen coordinates
- OCR
- screenshots for availability detection

This is important because those privileged mechanisms may not exist or be accessible during the real practical test.

---

# 12. Speed strategy

The goal is not to make the CPU loop run as many times as possible. The goal is to minimise the time between:

```text
availability becomes visible
          ↓
monitor detects it
          ↓
all cells selected
          ↓
reservation submitted
```

The current optimisations include:

### No full-page reload

The monitor presses the normal reservation-page refresh control instead of navigating the entire webpage.

### No artificial scan timer

After pressing Reload Availability, the monitor waits for the browser-visible grid change rather than sleeping for an arbitrary period.

### One browser-side selection operation

All currently available matching cells are selected together instead of issuing a separate Playwright click from Python for every cell.

### One reservation submission

Where multiple selection is supported, the selected cells are sent through the normal Reserve Selected action together.

### Immediate result handling

The monitor waits for the actual browser-visible response instead of assuming that a click means success.

### Continuous operation

A failed attempt or transient error does not end the program. It continues until Ctrl+C.

---

# 13. How the simulator's Reload Availability works

The simulator deliberately requires the normal human-facing Reload Availability button.

The server-side simulator can make new cells eligible for availability on its own schedule, but the reservation page does not automatically display those changes.

The user must request a refresh through the normal button.

This models the practical-test assumption that:

> **The reservation website does not automatically refresh its availability display. The user must press Reload Availability.**

The monitor therefore does the same thing a fast human-controlled browser could do, but removes unnecessary delays around the interaction.

---

# 14. When the real practical test arrives

Do not rewrite the whole program.

First inspect the real site and determine what is actually available to the browser.

Useful information may include:

1. HTML for the reservation grid.
2. HTML for one or more reservation cells.
3. The CSS classes/attributes used for availability.
4. HTML for the Reload Availability button.
5. HTML for the selection controls.
6. HTML for the Reserve/Book button.
7. The JavaScript that is actually available to the browser, if permitted to provide it.
8. Relevant browser-visible network behaviour, if needed and authorized.
9. What the page displays after a successful reservation.

You do **not** need to send us the entire website if the relevant pieces can be isolated.

We will then create a small website-specific configuration/adapter rather than rebuilding the monitoring engine.

For example, the simulator currently uses:

```python
BLOCK_SELECTOR = ".booking-block"
AVAILABLE_CLASS = "available"
REFRESH_BUTTON_SELECTOR = "#reloadGrid"
RESERVE_BUTTON_SELECTOR = "#reserveButton"
```

The real site will have different selectors. Those are the parts expected to change.

---

# 15. What we will investigate on the real site

The first question is:

**How does the browser learn that availability changed after Reload is pressed?**

Possible answers include:

### DOM update

JavaScript changes an existing element:

```text
unavailable → available
```

A browser-visible DOM observer may detect this immediately.

### DOM replacement

JavaScript replaces part or all of the grid.

We can observe the resulting DOM mutation and inspect the new cells.

### AJAX/fetch

The page requests updated availability and then changes the DOM.

We can determine whether the browser-visible response or resulting DOM gives us a better event to react to.

### WebSocket/SSE

The site may maintain a live browser connection. If this is actually how the site operates, we can investigate whether there is a legitimate browser-visible event we can use.

### Other mechanism

We adapt based on what the actual website does.

We do **not** assume the answer in advance.

---

# 16. Selector design

When adapting the monitor, prefer stable selectors such as:

```css
.booking-block
```

or:

```css
[data-cell-id]
```

or stable IDs/classes supplied by the website.

Avoid fragile generated selectors and screen coordinates whenever possible.

---

# 17. Persistent browser profile

The monitor uses:

```text
.browser-profile/
```

as a persistent Chromium profile.

This allows the browser session to persist between runs where appropriate.

The directory is excluded from Git because it may contain cookies and session information.

Do not commit it to the repository.

---

# 18. Troubleshooting

## Python command not found

Try:

```powershell
py --version
```

rather than `python --version` on Windows.

## Playwright is installed but Chromium is missing

Run:

```powershell
py -m playwright install chromium
```

## The monitor cannot find the reservation cells

Do not immediately change the Python logic.

Inspect the webpage and determine the actual cell selector and availability indicator first.

## The monitor selects the wrong cells

Check:

- `BLOCK_SELECTOR`
- `AVAILABLE_CLASS`
- `TARGET_TEXT`
- whether the website uses an attribute rather than a class

## The monitor clicks Reserve but reports failure

Check what the website actually displays after the click. The success indicator may be different from the simulator's:

```text
Reserved cells:
```

## The website changes the DOM but the monitor does not react

Inspect how the page updates the reservation grid. The real site may replace a container, use an iframe, or update a different element than expected.

---

# 19. Development philosophy

This project deliberately follows a **realistic-access principle**:

> If we would not reasonably have access to it during the practical test, we should not make the monitor depend on it now.

Our Cloudflare/D1 simulator exists to provide a controlled environment for testing, not to give the monitor an unfair shortcut.

That distinction is important.

We can use the simulator's server to **create test conditions**, but the monitor should behave as though the server belongs to somebody else.

---

# 20. Current project status

The project currently has:

- Cloudflare Workers simulator
- Cloudflare D1 shared state
- Three test accounts
- 40-cell reservation grid
- Manual Reload Availability behaviour
- Multi-cell selection
- Reservation logging
- Admin testing controls
- Persistent Playwright browser profile
- Continuous monitoring
- Error recovery
- Browser-visible DOM monitoring
- Fast all-cell selection
- No Admin Log access from the monitor
- No direct database/server access from the monitor

The next major development goal is to **benchmark the current monitor and remove any remaining unnecessary latency without compromising the realistic browser-only design**.

---

# 21. Licence

MIT License. See `LICENSE`.
