"""
Clipboard Share LAN Server

Manages an independent Flask server that binds to 0.0.0.0 for LAN access.
The main Flask app stays on 127.0.0.1; this server is started/stopped on demand.
Shares the same ClipboardService singleton (same process, same memory).
"""
import socket
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

_LAN_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Clipboard Share</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f7fa;color:#333;padding:20px;max-width:800px;margin:0 auto}
    h1{font-size:20px;font-weight:600;margin-bottom:16px;color:#1a1a1a;display:flex;align-items:center;gap:10px}
    .dot{width:10px;height:10px;border-radius:50%;background:#67c23a;display:inline-block}
    .card{background:#fff;border-radius:8px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
    .card-title{font-weight:500;margin-bottom:10px;font-size:14px;color:#555}
    textarea{width:100%;height:90px;padding:8px 10px;border:1px solid #dcdfe6;border-radius:6px;font-size:14px;resize:vertical;font-family:inherit;outline:none;transition:border .2s}
    textarea:focus{border-color:#409eff}
    .row{display:flex;gap:8px;align-items:center;margin-top:8px}
    button{background:#409eff;color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-size:13px;transition:background .15s}
    button:hover{background:#337ecc}
    button:active{background:#2b6cb0}
    .btn-sm{padding:4px 10px;font-size:12px;background:#f0f0f0;color:#555}
    .btn-sm:hover{background:#e0e0e0}
    #msg{font-size:13px;color:#67c23a}
    .item{border:1px solid #eef0f3;border-radius:6px;padding:10px 12px;margin-bottom:8px;position:relative}
    .item-meta{font-size:11px;color:#aaa;margin-bottom:4px}
    .item-content{font-size:13px;white-space:pre-wrap;word-break:break-all;max-height:120px;overflow:hidden}
    .item-content.expanded{max-height:none}
    .item-actions{display:flex;gap:6px;margin-top:6px}
    .empty{color:#999;font-size:13px;text-align:center;padding:20px 0}
    .hint{font-size:12px;color:#909399}
  </style>
</head>
<body>
  <h1><span class="dot"></span> Clipboard Share</h1>

  <div class="card">
    <div class="card-title">Paste content</div>
    <textarea id="input" placeholder="Paste here (Ctrl+V / Cmd+V) then press Submit or Ctrl+Enter"></textarea>
    <div class="row">
      <button onclick="submitContent()">Submit</button>
      <span class="hint">or Ctrl+Enter</span>
      <span id="msg"></span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">History <span id="count" style="color:#aaa;font-weight:400"></span></div>
    <div id="history"><div class="empty">Loading...</div></div>
  </div>

  <script>
    let items = [];

    async function loadHistory() {
      try {
        const res = await fetch('/api/history?limit=30');
        if (!res.ok) return;
        items = await res.json();
        renderHistory();
        document.querySelector('.dot').style.background = '#67c23a';
      } catch(e) {
        document.querySelector('.dot').style.background = '#f56c6c';
      }
    }

    function renderHistory() {
      const container = document.getElementById('history');
      document.getElementById('count').textContent = items.length > 0 ? '(' + items.length + ')' : '';
      if (items.length === 0) {
        container.innerHTML = '<div class="empty">No clipboard content yet</div>';
        return;
      }
      container.innerHTML = items.map((item, i) => {
        const ts = new Date(item.timestamp).toLocaleTimeString();
        const preview = escapeHtml(item.content.substring(0, 300));
        const hasMore = item.content.length > 300;
        return '<div class="item">' +
          '<div class="item-meta">#' + item.id + ' &middot; ' + escapeHtml(item.source) + ' &middot; ' + ts + '</div>' +
          '<div class="item-content" id="c' + i + '">' + preview + (hasMore ? '<span id="ell' + i + '">...</span>' : '') + '</div>' +
          '<div class="item-actions">' +
          '<button class="btn-sm" data-idx="' + i + '" onclick="copyItem(this)">Copy</button>' +
          (hasMore ? '<button class="btn-sm" data-idx="' + i + '" onclick="expandItem(this)">Show more</button>' : '') +
          '</div>' +
          '</div>';
      }).join('');
    }

    function copyItem(btn) {
      const i = parseInt(btn.dataset.idx);
      navigator.clipboard.writeText(items[i].content)
        .then(() => showMsg('Copied!'))
        .catch(() => {
          const el = document.createElement('textarea');
          el.value = items[i].content;
          document.body.appendChild(el);
          el.select();
          document.execCommand('copy');
          document.body.removeChild(el);
          showMsg('Copied!');
        });
    }

    function expandItem(btn) {
      const i = parseInt(btn.dataset.idx);
      const el = document.getElementById('c' + i);
      const ell = document.getElementById('ell' + i);
      el.classList.add('expanded');
      el.textContent = items[i].content;
      btn.remove();
    }

    async function submitContent() {
      const content = document.getElementById('input').value.trim();
      if (!content) return;
      try {
        const res = await fetch('/api/add', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({content, source: 'lan'})
        });
        if (res.ok) {
          document.getElementById('input').value = '';
          showMsg('Submitted!');
          await loadHistory();
        }
      } catch(e) { showMsg('Error: ' + e.message); }
    }

    function showMsg(msg) {
      const el = document.getElementById('msg');
      el.textContent = msg;
      setTimeout(() => { el.textContent = ''; }, 2000);
    }

    function escapeHtml(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    document.getElementById('input').addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submitContent();
    });

    loadHistory();
    setInterval(loadHistory, 2000);
  </script>
</body>
</html>"""


def _get_local_ip() -> str:
    """Detect the primary LAN IP without sending any data."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def _create_lan_app() -> Flask:
    """Minimal Flask app with clipboard REST routes for LAN access."""
    from .service import get_service
    from .websocket_service import broadcast_clipboard_update

    app = Flask(__name__)
    CORS(app)

    @app.route('/')
    def index():
        return _LAN_PAGE_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

    @app.route('/api/history')
    def history():
        limit = request.args.get('limit', 30, type=int)
        limit = max(1, min(limit, 100))
        return jsonify(get_service().get_history(limit))

    @app.route('/api/latest')
    def latest():
        item = get_service().get_latest()
        if item is None:
            return jsonify({'error': 'No clipboard content'}), 404
        return jsonify(item)

    @app.route('/api/add', methods=['POST'])
    def add():
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({'error': 'Missing content'}), 400
        try:
            item = get_service().add_content(data['content'], data.get('source', 'lan'))
            try:
                broadcast_clipboard_update(item)
            except Exception:
                pass
            return jsonify(item), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    return app


class LanServerManager:
    """Manages the Clipboard Share LAN server lifecycle in a background thread."""

    _instance = None

    def __init__(self):
        self._server = None
        self._thread = None
        self._port = None

    @classmethod
    def get_instance(cls) -> 'LanServerManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_local_ip(self) -> str:
        return _get_local_ip()

    def start(self, port: int = 50002) -> tuple[bool, str]:
        if self._server is not None:
            return False, 'Server already running'
        try:
            from werkzeug.serving import make_server
            lan_app = _create_lan_app()
            self._server = make_server('0.0.0.0', port, lan_app)
            self._port = port
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            ip = _get_local_ip()
            print(f'[ClipboardShare] LAN server started on http://{ip}:{port}')
            return True, f'http://{ip}:{port}'
        except Exception as e:
            self._server = None
            self._thread = None
            self._port = None
            print(f'[ClipboardShare] Failed to start LAN server: {e}')
            return False, str(e)

    def stop(self) -> tuple[bool, str]:
        if self._server is None:
            return False, 'Server not running'
        try:
            self._server.shutdown()
        except Exception:
            pass
        self._server = None
        self._thread = None
        old_port = self._port
        self._port = None
        print(f'[ClipboardShare] LAN server stopped (was port {old_port})')
        return True, 'Stopped'

    def get_status(self) -> dict:
        ip = _get_local_ip()
        running = self._server is not None
        return {
            'running': running,
            'port': self._port if running else None,
            'ip': ip,
            'url': f'http://{ip}:{self._port}' if running else None,
        }


def get_lan_server() -> LanServerManager:
    return LanServerManager.get_instance()
