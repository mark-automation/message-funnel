# MessageFunnel 📬

**Every platform inbox on one page.** A single-page web app that funnels
conversations from Messenger, Instagram, TikTok, WhatsApp, Telegram and X
into one unified inbox.

**Live:** https://mark-automation.github.io/message-funnel/

## What's in the box

| File | Purpose |
|---|---|
| `index.html` | App shell (no build step) |
| `styles.css` | Hand-written CSS; responsive at desktop / tablet / **390px phone width** |
| `data.js` | Connector layer + simulated demo conversations |
| `app.js` | Inbox logic: filters, search, threads, composer, unread counts |
| `api/` | FastAPI service for the future real-integration path (not required to run the Pages site) |

## Features

- Unified conversation list across all connectors, sorted by recency
- Per-platform filter rail with unread badges + global search
- Full thread view with day separators, timestamps, and a working composer
  (sent messages persist in `localStorage`, plus a simulated reply)
- Dark mode (auto + manual toggle), keyboard accessible, reduced-motion aware
- Mobile layout verified at 390px: single-pane navigation, 44px touch
  targets, 16px inputs (no iOS focus zoom)

## Honest scope: demo data vs. real integrations

The bundled connectors are **simulated** — sample conversations rendered
locally, timestamps relative to page load. Nothing leaves your browser.

Real pulls are a backend problem, not a frontend one:

- **Messenger + Instagram DMs**: Meta Graph API (`pages_messaging`,
  `instagram_manage_messages`) requires a business app review, webhooks for
  inbound messages, and an access token that must never ship to a static site.
- **TikTok**: DM APIs are tightly limited; most third-party access is not
  generally available.
- **WhatsApp**: needs WhatsApp Business Platform (Cloud API) with webhook
  verification.

Because of this, the architecture is ready: every connector implements

```js
{ id, name, color, icon, fetchConversations() -> [{ id, contact, unreadCount, messages }] }
```

Swapping a simulated connector for a real one means pointing
`fetchConversations()` at your own small token-holding backend
(e.g. a free-tier serverless function) that brokers OAuth and webhooks.
The UI does not change.

## Local development

Any static file server works:

```bash
cd message-funnel
python -m http.server 8080
# open http://localhost:8080
```

No dependencies, no package manager, no build chain.

## The `api/` service (optional, not deployed to Pages)

A FastAPI skeleton for the real-integration phase: unified
conversation/message schema, connector registry with the same mock
platforms, and Meta/TikTok webhook ingest + verification endpoints.

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --port 8800   # docs at /docs
```

The Pages site never calls it by default — it runs standalone on demo data.
