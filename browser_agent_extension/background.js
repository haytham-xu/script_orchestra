// Browser Agent — background service worker.
// Relaxes CORS for requests initiated from the local backend origin so the
// extension and the script_orchestra web UI can talk to :50001 freely.

// Load the command bridge (polls backend for tab ops requested from web UI).
importScripts('agent_bridge.js');

chrome.runtime.onInstalled.addListener(() => {
  console.log('[browser_agent] extension installed');
  chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: [1],
    addRules: [{
      id: 1,
      priority: 1,
      action: {
        type: 'modifyHeaders',
        responseHeaders: [
          { header: 'Access-Control-Allow-Origin', operation: 'set', value: '*' }
        ]
      },
      condition: {
        urlFilter: '*://127.0.0.1:50001/*',
        resourceTypes: ['xmlhttprequest']
      }
    }]
  });
});
