# Browser Agent — Chrome Extension

A thin "terminal" for the script_orchestra `browser_agent` tool. It collects
browser-side data (open tab URLs) and triggers backend features. All display
and management happen in the script_orchestra web UI (`/browser-agent`).

## Install (load unpacked)

1. Make sure the backend is running (`cd backend && python app.py`, port 50001).
2. Open Chrome → `chrome://extensions`
3. Toggle **Developer mode** (top-right).
4. Click **Load unpacked** and select this `browser_agent_extension/` folder.
5. Pin the extension; click its icon to open the popup.

## Features

- **Send all tabs to download queue** — collects every open http(s) tab URL and
  POSTs them to `/browser-agent/tabs`. The backend matches each against the
  configured site rules, resolves the download link, and queues it. Watch
  progress in the web UI.

## Adding a feature

The popup is an extensible launcher. To add a feature:

1. Create `features/<name>.js` and call `registerFeature({ id, label, run })`.
   `run()` may collect browser data (via `chrome.tabs`, `chrome.*`) and call
   `postJson('/browser-agent/...', body)`, or do a purely in-browser action.
2. Add `<script src="features/<name>.js"></script>` to `popup.html` before
   `popup.js`.

No changes to the core (`config.js`, `popup.js`) are needed.

## Config

Backend base URL is in `config.js` (`BACKEND_BASE = http://127.0.0.1:50001`).
Site rules / download directory are configured in the web UI Settings page,
not here.
