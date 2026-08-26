// Browser Agent — feature: batch tab download.
// Collects every open tab's URL and POSTs them to the backend, which
// matches them against configured site rules and queues downloads.
registerFeature({
  id: 'tab_downloader',
  label: 'Send all tabs to download queue',
  async run() {
    const tabs = await chrome.tabs.query({});
    const urls = tabs.map(t => t.url).filter(u => u && /^https?:/.test(u));
    if (urls.length === 0) return 'No http(s) tabs found.';
    const result = await postJson('/browser-agent/tabs', { tabs: urls });
    return `Sent ${urls.length} tab(s): ${result.added} added, ` +
           `${result.skipped} skipped, ${result.unmatched} unmatched.`;
  }
});
