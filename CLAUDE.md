# Script Orchestra — Project Guide

A self-hosted "toolbox" app: a **Flask (Python) backend** hosting ~16 independent tools, and a
**Vue 3 SPA frontend** that surfaces each tool as a page reachable from a dashboard.

- Backend runs on **port 50001** (`backend/app.py`, env `PORT`).
- Frontend dev server on **port 5001** (`npm run dev`), proxies `/api`, `/cypress`, `/socket.io` to backend.
- Frontend talks to backend at `http://127.0.0.1:50001` (`src/basic/Constants.ts`).

## Run

```bash
# backend
cd backend && source venv/bin/activate && python app.py    # :50001
# frontend
cd script-orchestra && npm install && npm run dev          # :5001
```

Build frontend: `npm run build`. Tests: `npm run test:e2e` (Cypress), `npm run test:unit` (Vitest, sparse).

---

## Backend architecture (`backend/`)

- **Bootstrap** `backend/app.py` → `create_app()`: enables CORS, inits shared Flask-RESTX `Api`
  (`backend/extensions.py`, `restx_api`, `doc=False`), registers each tool, adds `/health`.
- **Two registration styles coexist** (both fine):
  - Modern: `app.register_blueprint(<tool>_bp)` where the blueprint wraps a RESTX `Api` + `Namespace`.
  - Legacy (manga_*, pdf_converter, unzip, file_git): a `controller` module self-registers on the shared `restx_api`.
- **WebSocket**: ONE shared Socket.IO instance. `duplicate_finder` owns the canonical
  `df_websocket.init_socketio(app)`; that single `socketio` is then **passed into** every other tool's
  `websocket_service` (`fg_websocket`, `cs_websocket`, `cf_websocket`, `ba_websocket`, `wake_ws`, ...).
  Wiring lives in an `if socketio:` block in `app.py`. Do not create a second socketio.
- **DBs** init at startup: `<tool>_repo.init_db()` (browser_agent, memory_curve, knowledge_vault).
- **Config**: `backend/config.py` holds defaults and does `from config_local import *` to override
  with a gitignored `config_local.py`.

### Standard per-module layout
Newest modules (`memory_curve`, `knowledge_vault`) are the cleanest templates. A module = `backend/<tool>/`:
- `blueprint.py` — `Blueprint(url_prefix='/<tool-name>')`, wraps a RESTX `Api`, mounts the controller `Namespace`.
- `controller.py` — RESTX `Namespace` + `Resource` classes = the REST endpoints. Thin; delegates.
- `service.py` — business logic, usually a singleton via `get_service()`.
- `repository.py` — SQLite. **Self-healing schema**: a list of `CREATE TABLE IF NOT EXISTS` applied on
  every `_conn()`; `init_db()` called at startup.
- `entity.py` — plain data classes with `to_dict()` / `from_row()`.
- `settings_manager.py` — JSON `settings.json` with `DEFAULT_SETTINGS`, `load/save`, `validate_and_normalize`.
- `websocket_service.py` — `emit_progress` / broadcast helpers, guarded by `SOCKETIO_AVAILABLE`.

---

## Frontend architecture (`script-orchestra/src/`)

- **Vue 3** (Composition API) + **TypeScript**, **Vite 7**, **Element Plus** (auto-imported via
  `unplugin-vue-components` + `unplugin-auto-import` — `components.d.ts`/`auto-imports.d.ts` are generated).
  `vue-router` 4. Pinia installed but `stores/` is empty — state lives in component `setup()`.
- Libs: `axios`, `socket.io-client`, `vis-network`/`vis-data` (graphs), `marked`, `pdfjs-dist`, `vue-virtual-scroller`.
- **Entry** `src/main.ts` (Pinia + router + Element Plus + all EP icons). `src/App.vue` is a `<router-view>` shell.
- **Organized by feature module, not by type.** There is NO top-level `views/` or `components/`.
  Each tool = `src/<tool>/` with `views/` (the `.vue` page; larger ones split logic into a sibling
  `.ts` via `defineComponent({ name, setup() })`) and `service/` (`<Tool>Service.ts` + `Model.ts`).
- **API client**: shared `src/basic/RequestService.ts` exports `getRequest/postRequest/putRequest/deleteRequest`
  (axios wrappers, error toast via `ElMessage`). `src/basic/Constants.ts` holds `BACKEND_BASE_URL` and
  one `*_ENDPOINT` constant per tool. Each `service/<Tool>Service.ts` composes these; `Model.ts` holds interfaces.
- **Router** `src/router/index.ts` — one flat `routes` array; views eagerly imported. Path/name mirror the backend prefix.
- **Dashboard** `src/dashboard/views/OrchestraView.vue` — a `tools` array `{ key, name, path, testid? }`.
  Icons `src/dashboard/icons/toolIcons.ts` — inline SVG keyed by the same `key`.

⚠️ The manga-viewer frontend dir is misspelled `manga_viwer` on disk and in router imports. Leave it — fixing breaks imports.

---

## How to add a NEW tool end-to-end

Pick a name; the four identifiers must all mirror each other. Convention:
kebab-case for route/prefix/dashboard-key/endpoint-value; **snake_case for the module dirs**.
Example below uses `my-tool` / `my_tool`.

### Backend
1. Create `backend/my_tool/` from the `memory_curve` template:
   - `blueprint.py`: `my_tool_bp = Blueprint(...)` with `url_prefix='/my-tool'`, wrap in RESTX `Api`, mount controller `Namespace`.
   - `controller.py`: `Namespace` + `Resource` endpoint classes.
   - `service.py` (`get_service()` singleton), `repository.py` (self-healing schema + `init_db()`),
     `entity.py`, `settings_manager.py` as needed.
   - `websocket_service.py` only if the tool pushes realtime progress.
2. In `backend/app.py`:
   - Import and `app.register_blueprint(my_tool_bp)`.
   - Call `my_tool_repo.init_db()` at startup (near the other `init_db()` calls).
   - If it needs WebSockets, wire it inside the `if socketio:` block: pass the shared `socketio` to your `websocket_service`.

### Frontend
1. Create `src/my_tool/views/MyToolView.vue` (+ optional `MyToolView.ts`) and
   `src/my_tool/service/MyToolService.ts` + `service/Model.ts`.
2. Add `export const MY_TOOL_ENDPOINT = '/my-tool'` to `src/basic/Constants.ts`.
3. Add a route to `src/router/index.ts`: `{ path: '/my-tool', name: 'my-tool', component: MyToolView }`.
4. Register in the dashboard `tools` array (`OrchestraView.vue`): `{ key: 'my-tool', name: 'My Tool', path: '/my-tool' }`.
5. Add a matching inline-SVG badge keyed `'my-tool'` in `src/dashboard/icons/toolIcons.ts`.

---

## knowledge_vault (focus of recent work) — reference

AI-organized personal knowledge store. **Two layers**: raw fragments are the append-only source of truth
(user-only edits/deletes; AI never mutates them); the "knowledge network" (nodes + edges) is **derived and fully rebuildable**.

- Backend `backend/knowledge_vault/`, prefix `/knowledge-vault`:
  - `controller.py`: `/fragments` CRUD, `/fragments/batch-chat` (stateless conversational import → `{reply, fragments[], suggested_labels[]}`),
    `/fragments/batch` (commit), `/labels`, `/query` (pure vector recall, no token cost),
    `/query/ai` (recall + Claude answer), `POST /build` (async 202) + `GET /build/status` (polled),
    `/nodes`, `/edges`, `/lifecycle/stale`, `/backups`, `/settings`.
  - `ai_client.py`: calls the **Claude CLI directly** —
    `subprocess.run(["claude","--print","--model",MODEL, prompt], stdin=DEVNULL, timeout=...)`.
    No API key; uses the locally logged-in CLI. Model is user-configured in Settings
    (`ai_model`, or env `KV_MODEL`) — no baked-in default.
    `ask_text()` / `ask_json()` (extracts first balanced `{...}`, tolerates fences/prose).
  - `builder.py`: re-embed → vector-dedup (union-find, ≥0.97 auto-group) → materialize nodes →
    **batched** AI enrich titles/summaries (budget capped by `KV_AI_BUDGET`, `KV_CLASSIFY_BATCH` to stay fast/non-hanging) →
    relate into edges by similarity → recompute freshness. `get_status()`.
  - `embedder.py`: lazy `sentence-transformers` (embed model user-configured in Settings, L2-norm, HF offline after first cache).
  - `vector_store.py`: `VectorStore` iface + `SqliteVectorStore` (in-memory cosine).
  - `repository.py` SQLite tables: `raw_fragment, node, edge, fragment_vector, label, fragment_label`.
- Frontend `src/knowledge_vault/`: `views/KnowledgeVaultView.{vue,ts}` (tabs: capture | search | network | settings;
  `vis-network` graph), `service/{KnowledgeVaultService,Model}.ts`.

---

## Testing

- **Cypress E2E** is primary. Config `script-orchestra/cypress.config.js`; specs in `cypress/e2e/<tool>/`
  (currently duplicate-finder, manga-viewer, pdf-converter, photo-classifier, unzip — newer tools lack specs).
  Standards: `cypress/cypress-e2e/CYPRESS_STANDARDS.md`. Scripts: `test:e2e`, `test:e2e:open`, `test:e2e:<tool>`.
- **Backend Cypress support** `backend/cypress_support/` (`api.py`, `config_manager.py` snapshot/restore).
  `app.py` warns on unrestored config snapshots at startup.
- **Unit**: Vitest configured but sparse. Backend has ad-hoc `test_*.py` scripts, no formal pytest suite.

## Key files
- Backend: `backend/app.py`, `backend/extensions.py`, `backend/config.py`
- Frontend entry/router: `src/main.ts`, `src/router/index.ts`, `vite.config.ts`
- Frontend shared: `src/basic/{RequestService,Constants}.ts`
- Dashboard: `src/dashboard/views/OrchestraView.vue`, `src/dashboard/icons/toolIcons.ts`
