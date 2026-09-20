// Browser Agent — command bridge.
// Polls the backend for RPC-style commands issued by the web UI (chrome.tabs
// operations only the extension can perform), executes them, and posts the
// result back. Kept intentionally small — new tools just add another case in
// executeCommand.

const BACKEND_BASE = 'http://127.0.0.1:50001';
const EXTENSION_VERSION = chrome.runtime.getManifest().version;
const BRIDGE_CAPABILITIES = [
  'list_tabs',
  'close_tabs',
  'open_tabs',
  'focus_tabs',
  'merge_tabs',
  'group_tabs_by_domain',
  'get_cookies_for_domain',
  'sort_tabs_by_group',
  'split_tabs_by_groups',
  'record_activations',
  'get_bookmarks',
  'write_bookmarks',
  'move_tab',
];
// Short poll interval keeps the MV3 service worker "actively doing work"
// (fetch counts as activity), reducing the window Chrome can suspend us in.
// Alarm fallback below still catches the case when the worker is fully
// evicted despite this.
const POLL_INTERVAL_MS = 2000;

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
      const closedIds = [];
      const failed = [];
      for (const rawId of ids) {
        const tabId = Number(rawId);
        if (!Number.isInteger(tabId) || tabId <= 0) {
          failed.push({ tab_id: rawId, error: 'invalid_tab_id' });
          continue;
        }
        try {
          await chrome.tabs.remove(tabId);
          closedIds.push(tabId);
        } catch (e) {
          failed.push({
            tab_id: tabId,
            error: (e && e.message) || String(e),
          });
        }
      }
      return {
        result: {
          closed: closedIds.length,
          closed_ids: closedIds,
          failed,
        }
      };
    }
    if (cmd.type === 'open_tabs') {
      const params = cmd.params || {};
      const items = Array.isArray(params.items) ? params.items : [];
      const destination = params.destination === 'current_window' ? 'current_window' : 'new_window';

      const results = [];
      let targetWindowId = null;

      if (destination === 'current_window') {
        const focused = await chrome.windows.getLastFocused({ populate: false });
        targetWindowId = focused && focused.id ? focused.id : null;
      }

      for (let i = 0; i < items.length; i++) {
        const item = items[i] || {};
        const recordId = Number(item.record_id || 0);
        const url = String(item.url || '').trim();
        if (!url) {
          results.push({
            record_id: recordId,
            url,
            ok: false,
            tab_id: null,
            error: 'missing_url',
          });
          continue;
        }

        try {
          let tab = null;
          if (destination === 'new_window') {
            if (targetWindowId === null) {
              const created = await chrome.windows.create({ url, focused: true });
              targetWindowId = created && created.id ? created.id : null;
              tab = (created && created.tabs && created.tabs[0]) || null;
            } else {
              tab = await chrome.tabs.create({ windowId: targetWindowId, url, active: false });
            }
          } else {
            if (targetWindowId !== null) {
              tab = await chrome.tabs.create({ windowId: targetWindowId, url, active: false });
            } else {
              tab = await chrome.tabs.create({ url, active: false });
            }
          }

          results.push({
            record_id: recordId,
            url,
            ok: true,
            tab_id: tab && tab.id ? tab.id : null,
            error: '',
          });
        } catch (e) {
          results.push({
            record_id: recordId,
            url,
            ok: false,
            tab_id: null,
            error: (e && e.message) || String(e),
          });
        }
      }

      return {
        result: {
          destination,
          results,
        }
      };
    }
    if (cmd.type === 'focus_tabs') {
      const ids = (cmd.params && cmd.params.tab_ids) || [];
      const results = [];
      for (const rawId of ids) {
        const tabId = Number(rawId);
        if (!Number.isInteger(tabId) || tabId <= 0) {
          results.push({ tab_id: rawId, ok: false, error: 'invalid_tab_id' });
          continue;
        }
        try {
          const tab = await chrome.tabs.get(tabId);
          await chrome.tabs.update(tabId, { active: true });
          if (tab && tab.windowId) {
            await chrome.windows.update(tab.windowId, { focused: true });
          }
          results.push({ tab_id: tabId, ok: true, error: '' });
        } catch (e) {
          results.push({
            tab_id: tabId,
            ok: false,
            error: (e && e.message) || String(e),
          });
        }
      }
      return { result: { results } };
    }
    if (cmd.type === 'merge_tabs') {
      // Move every tab into a single window — the one that already has the most
      // tabs (fewest moves). Pinned tabs stay pinned; Chrome keeps them at the
      // front automatically, so we move pinned first, then the rest.
      const all = await chrome.tabs.query({});
      if (all.length === 0) return { result: { moved: 0, windowId: null } };
      const byWin = {};
      for (const t of all) (byWin[t.windowId] = byWin[t.windowId] || []).push(t);
      // target = window with the most tabs
      let target = all[0].windowId, best = -1;
      for (const [win, tabs] of Object.entries(byWin)) {
        if (tabs.length > best) { best = tabs.length; target = Number(win); }
      }
      const movers = all.filter(t => t.windowId !== target);
      // pinned first so Chrome doesn't drop the pinned flag on reorder
      const pinned = movers.filter(t => t.pinned).map(t => t.id);
      const normal = movers.filter(t => !t.pinned).map(t => t.id);
      if (pinned.length) await chrome.tabs.move(pinned, { windowId: target, index: -1 });
      if (normal.length) await chrome.tabs.move(normal, { windowId: target, index: -1 });
      return { result: { moved: movers.length, windowId: target } };
    }
    if (cmd.type === 'group_tabs_by_domain') {
      // Within the focused window, reorder tabs so same-domain tabs are adjacent.
      // Pinned tabs are left untouched at the front (their relative order kept).
      const focused = await chrome.windows.getLastFocused({ populate: false });
      const winId = focused && focused.id;
      const tabs = await chrome.tabs.query({ windowId: winId });
      const domainOf = (url) => {
        try { return new URL(url).hostname || url; } catch { return url || ''; }
      };
      const movable = tabs.filter(t => !t.pinned);
      const pinnedCount = tabs.length - movable.length;
      // stable group: sort by domain, ties keep original tab index
      const sorted = [...movable].sort((a, b) => {
        const d = domainOf(a.url).localeCompare(domainOf(b.url));
        return d !== 0 ? d : a.index - b.index;
      });
      // place them right after the pinned block, in sorted order
      for (let i = 0; i < sorted.length; i++) {
        await chrome.tabs.move(sorted[i].id, { index: pinnedCount + i });
      }
      return { result: { grouped: sorted.length, windowId: winId } };
    }
    if (cmd.type === 'sort_tabs_by_group') {
      // params: { window_id: int, group_order: [{tab_id, is_separator}] }
      // group_order is the backend-computed desired sequence: grouped tabs in
      // group-name order, with is_separator:true sentinels between groups,
      // then ungrouped tabs last. Pinned tabs are left at the front untouched.
      const windowId = Number((cmd.params && cmd.params.window_id) || 0);
      const groupOrder = (cmd.params && cmd.params.group_order) || [];
      const tabs = await chrome.tabs.query({ windowId });
      const pinnedCount = tabs.filter(t => t.pinned).length;
      let insertIdx = pinnedCount;
      let sortedCount = 0;
      for (const entry of groupOrder) {
        if (entry.is_separator) {
          await chrome.tabs.create({ windowId, index: insertIdx, url: 'about:blank', active: false });
          insertIdx++;
        } else {
          const tabId = Number(entry.tab_id);
          if (Number.isInteger(tabId) && tabId > 0) {
            await chrome.tabs.move(tabId, { windowId, index: insertIdx });
            insertIdx++;
            sortedCount++;
          }
        }
      }
      return { result: { sorted: sortedCount, windowId } };
    }
    if (cmd.type === 'split_tabs_by_groups') {
      // params: { groups: [{group_id, group_name, tab_ids: [int]}] }
      // Each group's tabs are moved into a new dedicated window.
      // Tabs not listed (ungrouped) stay in their original windows.
      const groupList = (cmd.params && cmd.params.groups) || [];
      let windowsCreated = 0;
      for (const grp of groupList) {
        const ids = (grp.tab_ids || []).map(Number).filter(n => Number.isInteger(n) && n > 0);
        if (ids.length === 0) continue;
        try {
          const newWin = await chrome.windows.create({ tabId: ids[0], focused: false });
          if (ids.length > 1 && newWin && newWin.id) {
            await chrome.tabs.move(ids.slice(1), { windowId: newWin.id, index: -1 });
          }
          windowsCreated++;
        } catch (e) {
          // Skip groups whose tabs can't be moved (e.g. already closed).
        }
      }
      return { result: { windows_created: windowsCreated } };
    }
    if (cmd.type === 'get_cookies_for_domain') {
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
    if (cmd.type === 'get_bookmarks') {
      const tree = await chrome.bookmarks.getTree();
      return { result: { tree } };
    }
    if (cmd.type === 'write_bookmarks') {
      // params: either
      //   { tree: [<node>...] }  where <node> is a folder
      //       { folder, bookmark_id?, items: [{bookmark_id,url,title}], children: [<node>...] }
      //       or a bare item { bookmark_id?, url, title } (ungrouped, top level), OR
      //   { items: [{bookmark_id,url,title}] }  (legacy flat form).
      // Folders: reuse bookmark_id if it still resolves, else create under parentId.
      // Items: update if bookmark_id resolves, else create under parentId.
      const results = [];

      async function writeItem(item, parentId) {
        try {
          if (item.bookmark_id) {
            try {
              await chrome.bookmarks.update(item.bookmark_id, { title: item.title || item.url, url: item.url });
              results.push({ bookmark_id: item.bookmark_id, ok: true, action: 'updated' });
              return;
            } catch (_) {}
          }
          const createOpts = { title: item.title || item.url, url: item.url };
          if (parentId) createOpts.parentId = parentId;
          const created = await chrome.bookmarks.create(createOpts);
          results.push({ bookmark_id: created.id, ok: true, action: 'created' });
        } catch (e) {
          results.push({ bookmark_id: item.bookmark_id || null, ok: false, error: (e && e.message) || String(e) });
        }
      }

      async function writeFolder(node, parentId) {
        let folderId = null;
        try {
          if (node.bookmark_id) {
            try {
              const existing = await chrome.bookmarks.get(node.bookmark_id);
              if (existing && existing.length && !existing[0].url) {
                folderId = node.bookmark_id;
                await chrome.bookmarks.update(folderId, { title: node.folder });
              }
            } catch (_) {}
          }
          if (!folderId) {
            const createOpts = { title: node.folder };
            if (parentId) createOpts.parentId = parentId;
            const createdFolder = await chrome.bookmarks.create(createOpts);
            folderId = createdFolder.id;
          }
          results.push({ bookmark_id: folderId, ok: true, action: 'folder' });
        } catch (e) {
          results.push({ bookmark_id: node.bookmark_id || null, ok: false, error: (e && e.message) || String(e) });
          return;
        }
        for (const item of node.items || []) {
          await writeItem(item, folderId);
        }
        for (const child of node.children || []) {
          await writeNode(child, folderId);
        }
      }

      async function writeNode(node, parentId) {
        if (node && node.folder !== undefined) {
          await writeFolder(node, parentId);
        } else if (node && node.url) {
          await writeItem(node, parentId);
        }
      }

      const tree = cmd.params && cmd.params.tree;
      if (Array.isArray(tree)) {
        for (const node of tree) {
          await writeNode(node, null);
        }
      } else {
        const items = (cmd.params && cmd.params.items) || [];
        for (const item of items) {
          await writeItem(item, null);
        }
      }
      return { result: { results } };
    }
    if (cmd.type === 'move_tab') {
      // params: { tab_id: int, index: int, window_id?: int }
      // Moves a single tab to the given index within its current window (or
      // window_id if provided). Pinned tabs cannot be moved to non-pinned
      // positions — Chrome silently clamps the index; we just pass through.
      const tabId = Number((cmd.params && cmd.params.tab_id) || 0);
      const index = Number((cmd.params && cmd.params.index) !== undefined ? cmd.params.index : -1);
      if (!Number.isInteger(tabId) || tabId <= 0) return { error: 'invalid tab_id' };
      const moveOpts = { index };
      if (cmd.params && cmd.params.window_id) moveOpts.windowId = Number(cmd.params.window_id);
      const moved = await chrome.tabs.move(tabId, moveOpts);
      const result = Array.isArray(moved) ? moved[0] : moved;
      return { result: { tab_id: tabId, new_index: result && result.index } };
    }
    return { error: `unknown command type: ${cmd.type}` };
  } catch (e) {
    return { error: (e && e.message) || String(e) };
  }
}

// --- Tab activation heat tracking ---
// Accumulates per-URL activation counts in memory and flushes to the backend
// every 30 s. Survives service-worker suspension because the batch is declared
// at module scope; on SW revival the batch is empty but future activations keep
// flowing.

const _activationBatch = {}; // url -> { activation_count, last_activated_at }

chrome.tabs.onActivated.addListener(async (info) => {
  try {
    const tab = await chrome.tabs.get(info.tabId);
    const url = tab && tab.url;
    if (!url || url.startsWith('chrome://') || url.startsWith('about:')) return;
    const now = new Date().toISOString();
    if (_activationBatch[url]) {
      _activationBatch[url].activation_count += 1;
      _activationBatch[url].last_activated_at = now;
    } else {
      _activationBatch[url] = { activation_count: 1, last_activated_at: now };
    }
  } catch (_) {}
});

async function flushActivations() {
  const entries = Object.entries(_activationBatch);
  if (entries.length === 0) return;
  const activations = entries.map(([url, v]) => ({
    url,
    activation_count: v.activation_count,
    last_activated_at: v.last_activated_at,
  }));
  // Clear before sending so a failed flush doesn't block future accumulation.
  for (const url of Object.keys(_activationBatch)) delete _activationBatch[url];
  try {
    await fetch(`${BACKEND_BASE}/browser-agent/tab-archive/live-tabs/record-activations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activations }),
    });
  } catch (_) {}
}

setInterval(flushActivations, 30000);

async function pollLoop() {
  while (true) {
    try {
      const query = new URLSearchParams({
        extension_version: EXTENSION_VERSION,
        capabilities: BRIDGE_CAPABILITIES.join(','),
      });
      const r = await fetch(`${BACKEND_BASE}/browser-agent/agent/commands?${query.toString()}`);
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
