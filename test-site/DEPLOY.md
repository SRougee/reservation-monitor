# Deploying the Test Site to Cloudflare

This test site uses the current Cloudflare **Workers Static Assets** model, with a Worker API and D1 database. Cloudflare's current documentation calls the static asset location the `assets.directory`; this is the setting that tells Wrangler exactly where the website files are.

## Repository layout

```text
test-site/
├── public/              <-- WEBSITE FILES: HTML/CSS/JS
│   ├── index.html
│   ├── landing.html
│   ├── dummy.html
│   ├── reservation.html
│   ├── admin.html
│   ├── app.js
│   └── styles.css
├── worker/
│   └── index.js         <-- Worker API
├── schema.sql           <-- D1 database schema
├── wrangler.toml        <-- Cloudflare deployment specification
└── package.json
```

**Do not point the Cloudflare deployment at the repository root.** The static website directory is:

```text
./public
```

relative to `test-site/wrangler.toml`.

## 1. Install Wrangler

From `test-site`:

```bash
npm install
```

Or use the latest Wrangler directly:

```bash
npx wrangler@latest --version
```

## 2. Log in

```bash
npx wrangler login
```

## 3. Create the D1 database

```bash
npx wrangler d1 create reservation-monitor-test
```

Cloudflare will return a database ID. Copy it into:

```text
wrangler.toml
```

replacing:

```toml
database_id = "<YOUR-D1-DATABASE-ID>"
```

## 4. Initialise the database

Run:

```bash
npx wrangler d1 execute reservation-monitor-test --remote --file=./schema.sql
```

The schema creates the three test accounts, 40 cells, sessions, and the reservation log.

## 5. Deploy

```bash
npx wrangler deploy
```

Wrangler will deploy the Worker and the static assets from `./public` as one application.

## 6. Test accounts

```text
testuser / test123
admin   / admin123
monitor / monitor123
```

These are intentionally hardcoded because this is a simulation. Do not use this authentication design for production.

## 7. Three-browser test

### Browser 1 — test user

Log in as:

```text
testuser / test123
```

Navigate to `/reservation.html`.

### Browser 2 — administrator

Log in as:

```text
admin / admin123
```

Navigate to `/admin.html`.

Use **Open Random Cells** or **Open Cell** to create controlled availability and watch the reservation log.

### Browser 3 — monitor

Configure the Playwright monitor to use the deployed test-site URL. Log in as:

```text
monitor / monitor123
```

Then navigate to the reservation page.

## Why the Reload button is partial

The reservation page deliberately does not perform a browser-level full-page reload when **Reload Availability** is clicked. It calls `/api/state` and redraws only the 40-cell grid.

This simulates a real booking site that refreshes only the relevant availability component to reduce unnecessary page work.

The monitor itself can still perform its configured page reload cycle. That lets us test how the monitor behaves against a site whose human-facing reload mechanism is partial.

## 30-second availability behaviour

The Worker uses a 30-second cycle. On the first state request in a new cycle it randomly changes 1-4 currently grey, non-red cells to `available`.

White cells remain available until someone reserves them. Red cells 1-8 are permanently unavailable.

The opening timestamp is stored in D1. When a cell is reserved, the Worker records the opening time, reservation time, calculated open duration, and username.

## Local testing

From `test-site`:

```bash
npx wrangler dev
```

Wrangler will provide a local URL. D1 is locally simulated during normal local development unless you explicitly configure a remote binding.

## Cloudflare configuration reference

`wrangler.toml` contains the important deployment specification:

```toml
[assets]
directory = "./public"
binding = "ASSETS"
run_worker_first = ["/api/*"]
```

The Worker handles `/api/*`, while Cloudflare serves the files in `public/` as static assets.
