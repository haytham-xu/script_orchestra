# Script Orchestra

A local desktop-style toolbox: a Python (Flask) backend and a Vue 3 frontend, each tool
accessible from a dashboard. Tools include Manga Classifier, Manga Viewer, Photo Classifier,
Duplicate Finder, File-Git, Roadmap, and more.

## Requirements

- Python 3.11+ (3.13 recommended)
- Node.js 20+ (22 recommended)

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv venv

# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1

pip install -r requirements.txt
python app.py
```

Backend runs on `http://localhost:5001`. See [backend/README.md](backend/README.md) for details.

### 2. Frontend

```bash
cd script-orchestra
npm install
npm run dev
```

Open `http://localhost:5173/` and pick a tool from the dashboard.

## Common commands

| Task | Command |
|------|---------|
| Install backend deps | `pip install -r requirements.txt` (inside venv) |
| Freeze backend deps | `pip freeze > requirements.txt` |
| Run backend | `python app.py` |
| Install frontend deps | `npm install` |
| Run frontend (dev) | `npm run dev` |
| Build frontend | `npm run build` |

## Todo

* Cypress for all tools
* File-Git real cloud provider (Baidu) integration
