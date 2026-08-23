# Message Funnel

**One page for every inbox.** A unified messaging dashboard that pulls
conversations from Messenger, Instagram, TikTok, WhatsApp, Telegram and X
into a single normalized stream — one thread list, one chat pane, zero tab
switching.

> Demo build: the Pages frontend renders deterministic demo traffic.
> Connectors are swappable adapters — the ingest path (webhook normalizers)
> is already testable before platform credentials exist.

## Architecture

```
┌────────────────────┐     REST/JSON      ┌─────────────────────────┐
│  Frontend (Pages)  │ ◄────────────────► │  API service (FastAPI)  │
│  static demo data  │   /api/conversations│  connector registry    │
│  + live-API mode   │   /api/webhooks/*  │  webhook normalizers    │
└────────────────────┘                    └─────────────────────────┘
```

- **`index.html` / `styles.css` / `app.js` / `data.js`** — static frontend.
  Set `window.MF_API_BASE` before `app.js` loads to point it at a live API;
  without it, the demo dataset (`data.js`, mirroring the API seed) is served.
- **`api/main.py`** — FastAPI service: unified conversation/message store,
  send endpoint, per-platform webhooks with Meta handshake support.
- **`api/connectors.py`** — platform registry + adapter contract.
  `MockConnector` serves demo traffic today; Meta/TikTok adapters normalize
  real webhook payloads now and fetch once credentials are provisioned.

## Run locally

Frontend (any static server):

```bash
python -m http.server 8080
# open http://localhost:8080
```

Backend:

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --port 8800
# docs at http://localhost:8800/docs
```

Point the frontend at it: set `window.MF_API_BASE = "http://localhost:8800"`.

## Platform notes (v2)

| Platform | Route | Status |
|---|---|---|
| Messenger / Instagram | Meta Graph API — app review + Page/business assets | webhook normalization ready |
| TikTok | Business Messaging API (approval required) | normalizer skeleton ready |
| WhatsApp / Telegram / X | straightforward APIs | mock connectors |

Webhooks need a stable public HTTPS endpoint — free tiers that sleep will
silently drop messages, so plan for one always-on box.
