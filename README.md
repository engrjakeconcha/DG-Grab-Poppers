# Daddy Grab Super App

This repository now contains the Daddy Grab platform build:

- Telegram bot for disclaimer, redirect, notifications, and broadcasts
- GitHub Pages landing page in `/docs`
- Vercel storefront for `store.daddygrab.online`
- Droplet-ready storefront API runtime for `store.daddygrab.online`

## Current Storefront Scope

- Daddy Grab-only branding and routes
- Supabase-backed catalog, checkout, order tracking, promos, and admin
- No Google Sheets dependency for the storefront
- No Retell or AI agent in this phase
- Lalamove and PayMongo frameworks left inactive for future activation

## Storefront Routes

- `/` storefront catalog
- `/checkout`
- `/track`
- `/address`
- `/admin`

## Droplet Runtime

- `storefront-api-server.js` runs the storefront API locally on the droplet
- `deploy/daddygrab-storefront-api.service` manages the API as a systemd service
- `deploy/daddygrab-storefront-nginx.conf` serves the static storefront and proxies `/api/*`
- `scripts/deploy_storefront_droplet.sh` deploys the storefront runtime to `157.230.194.50`

For droplet deployment, keep secrets in an untracked `.env.storefront` file and deploy that file separately.

## Seeded Setup

- Test products for `poppers`, `supplements`, `toys`, and `lubricants`
- Test promo code: `DADDYTEST10`
- Seeded admins:
  - `Em` / `101010` / `super_admin`
  - `Admin1` / `010101` / `admin`

Rotate seeded passwords before production.
