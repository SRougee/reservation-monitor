# Reservation Monitor Test Site

This directory contains the Cloudflare-ready simulated reservation website used to test `reservation_monitor.py`.

## Cloudflare deployment layout

The test site is designed for **Cloudflare Pages + Cloudflare Workers + D1**.

- `public/` — all browser-facing static website files. This is the **Pages build/output directory** and must be explicitly configured as the directory Cloudflare deploys.
- `worker/` — Cloudflare Worker API source. This is deployed separately as the Worker entry point.
- `schema.sql` — D1 database schema.
- `wrangler.toml` — Wrangler configuration, including the Worker entry point, Pages directory, and D1 binding.

### Important Cloudflare file-location specification

When configuring Cloudflare, do not point the deployment at the repository root. The website files are in:

```text
reservation-monitor/test-site/public/
```

The Worker source is in:

```text
reservation-monitor/test-site/worker/index.js
```

The D1 schema is:

```text
reservation-monitor/test-site/schema.sql
```

This explicit structure is intentional so Cloudflare knows exactly where the website files and Worker code live.

## Simulated accounts

This is a test environment only. Passwords are deliberately hardcoded and **not hashed**, as requested.

- `testuser` / `test123`
- `admin` / `admin123`
- `monitor` / `monitor123`

Never reuse these credentials on a real service.
