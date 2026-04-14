# Daddy Grab Super App Telegram Bot

This repo contains the staged Telegram bot clone for Daddy Grab Super App, built from the JCIT storefront bot architecture and pointed at the Daddy Grab Mini App at [http://daddygrab.online/](http://daddygrab.online/).

## Files
- `bot.py` main polling bot
- `webhook_app.py` optional Flask webhook bridge
- `config.py` bot identity, URLs, runtime paths, and sheet settings
- `requirements.txt` Python dependencies
- `assets/` start and completion images

## Local run
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Runtime defaults
- Bot username defaults to `@DGrabstgbot`
- Mini App URL defaults to `http://daddygrab.online/`
- Admin URL defaults to `http://daddygrab.online/admin`
- Runtime state defaults to `/opt/daddygrab-super-app`

## Google Sheets behavior
The bot will:
- Open `GSHEET_ID` when provided
- Otherwise open `GSHEET_NAME`
- Create a fresh spreadsheet automatically when `GSHEET_NAME` does not exist yet

The bot also auto-creates worksheets such as `Products`, `Promos`, `Users`, `Orders`, `Tickets`, `Affiliates`, and `BroadcastLog`.

## Deployment notes
- Target droplet: `157.230.194.50`
- GitHub repo: [DG-Grab-Poppers](https://github.com/engrjakeconcha/DG-Grab-Poppers)
- Before production, move secrets like the Telegram token and service account JSON to environment variables
