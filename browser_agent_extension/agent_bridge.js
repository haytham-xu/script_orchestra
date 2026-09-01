// Browser Agent — command bridge.
// Polls the backend for RPC-style commands issued by the web UI (chrome.tabs
// operations only the extension can perform), executes them, and posts the
// result back. Kept intentionally small — new tools just add another case in
// executeCommand.

const BACKEND_BASE = 'http://127.0.0.1:50001';
// Short poll interval keeps the MV3 service worker "actively doing work"
// (fetch counts as activity), reducing the window Chrome can suspend us in.
// Alarm fallback below still catches the case when the worker is fully
// evicted despite this.
const POLL_INTERVAL_MS = 200;

async function executeCommand(cmd) {
  try {
    if (cmd.type === 'list_tabs') {
      const tabs = await chrome.tabs.query({});
      return {
        result: {
          tabs: tabs.map(t => ({
            id: t.id,
            title: t.title || '',
            url: t.url || '',
            windowId: t.windowId,
            active: !!t.active,
            pinned: !!t.pinned,
            favIconUrl: t.favIconUrl || '',
          }))
        }
      };
    }
    if (cmd.type === 'close_tabs') {
      const ids = (cmd.params && cmd.params.tab_ids) || [];
      await chrome.tabs.remove(ids);
      return { result: { closed: ids.length } };
    }
    if (cmd.type === 'get_cookies_for_domain') {
      // Read every cookie whose domain matches. Chrome's API scopes by
      // `domain`; we intentionally return ALL of them (including HttpOnly)
      // so the backend can replay the user's browser session verbatim.
      const domain = (cmd.params && cmd.params.domain) || '';
      if (!domain) return { error: 'domain is required' };
      const cookies = await chrome.cookies.getAll({ domain });
      // Also grab the standard User-Agent from navigator so the backend can
      // pin its Session to the same UA the site fingerprinted.
      const userAgent = (self.navigator && self.navigator.userAgent) || '';
      return {
        result: {
          domain,
          userAgent,
          cookies: cookies.map(c => ({
            name: c.name,
            value: c.value,
            domain: c.domain,
            path: c.path,
            secure: !!c.secure,
            httpOnly: !!c.httpOnly,
            sameSite: c.sameSite || 'unspecified',
            expirationDate: c.expirationDate || null,
          })),
        },
      };
    }
    return { error: `unknown command type: ${cmd.type}` };
  } catch (e) {
    return { error: (e && e.message) || String(e) };
  }
}

async function pollLoop() {
  while (true) {
    try {
      const r = await fetch(`${BACKEND_BASE}/browser-agent/agent/commands`);
      if (r.ok) {
        const { commands } = await r.json();
        if (Array.isArray(commands) && commands.length) {
          await Promise.all(commands.map(async (cmd) => {
            const outcome = await executeCommand(cmd);
            try {
              await fetch(`${BACKEND_BASE}/browser-agent/agent/results/${cmd.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(outcome),
              });
            } catch (e) {
              console.warn('[browser_agent] failed to post result', e);
            }
          }));
        }
      }
    } catch (e) {
      // Backend down or unreachable — just back off and retry.
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

// Kick off on both install and every service-worker wake-up. Continuous fetch
// inside pollLoop keeps the SW alive under MV3, but only WHILE the SW is
// running — if Chrome ever terminates the SW (idle, memory pressure), the
// loop dies with it and nothing wakes it back up. chrome.alarms fixes that:
// an alarm firing revives the SW, this script re-runs top to bottom, and
// pollLoop() starts fresh.

// Guard against starting two loops in the same SW lifetime (paranoia — this
// script only runs once per SW wake, so it shouldn't happen normally).
let _pollRunning = false;
async function startPollLoop() {
  if (_pollRunning) return;
  _pollRunning = true;
  try {
    await pollLoop();
  } finally {
    _pollRunning = false;
  }
}

chrome.alarms.create('browser-agent-keepalive', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'browser-agent-keepalive') startPollLoop();
});

startPollLoop();
