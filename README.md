# FFWD Trailer Kitchen v0.7.0 🍳

> *Agentic Video Highlight Platform*

Video Kitchen v0.7.0 transforms video into highlights, teasers, and social clips using an AI-powered pipeline with a full REST API and web dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Video Kitchen v0.7.0                    │
├─────────────────────────────────────────────────────┤
│  Dashboard (HTML) │  OpenClaw Agent  │  CLI (Python) │
├─────────────────────────────────────────────────────┤
│              Express REST API (Node.js)               │
│  /projects CRUD  │  /jobs Queue/Run  │  /kitchen/tools │
├─────────────────────────────────────────────────────┤
│              SQLite Database                          │
│  projects │ scenes │ jobs │ outputs │ recipes         │
├─────────────────────────────────────────────────────┤
│              Python Pipeline Engine                   │
│  prep → scoring → select → plate → season → qc       │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone & install Python deps
git clone https://github.com/snyderline0987/VideoKitchen.git
cd VideoKitchen
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Install backend
cd backend
npm install
node scripts/init-db.js
node scripts/seed-recipes.js

# 3. Start API server
node server.js
# → http://localhost:3001

# 4. Open dashboard
cd ../dashboard
open index.html
```

## Python Pipeline (CLI)

```bash
# Full auto
.venv/bin/python3 scripts/kitchen.py --open video.mp4 --recipe social_teaser_w24 --auto

# Step by step
.venv/bin/python3 scripts/kitchen.py --open video.mp4 --transcribe
.venv/bin/python3 scripts/kitchen.py --analyze --project my_project
.venv/bin/python3 scripts/kitchen.py --select --auto --recipe spicy_trailer --project my_project
.venv/bin/python3 scripts/kitchen.py --plate --project my_project
.venv/bin/python3 scripts/kitchen.py --season --vo "Check this out!" --project my_project
.venv/bin/python3 scripts/kitchen.py --qc --project my_project
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/projects` | GET/POST | List/Create projects |
| `/api/projects/:id` | GET/PATCH/DELETE | Project CRUD |
| `/api/jobs` | GET/POST | List/Create jobs |
| `/api/jobs/:id` | GET | Job status + logs |
| `/api/jobs/:id/run` | POST | Execute pipeline job |
| `/api/kitchen/tools/:tool` | POST | OpenClaw tool integration |
| `/api/recipes` | GET | List recipes |
| `/api/outputs` | GET | List outputs |

## Pipeline Stages

| Stage | Script | Description |
|-------|--------|-------------|
| **Prep** | `prep_station.py` | Scene detection (PySceneDetect), thumbnails, transcription |
| **Analyze** | `scoring.py` | AI scoring — visual, transcript, audio energy |
| **Select** | `kitchen.py --select` | Auto-select top scenes by recipe criteria |
| **Plate** | `plating.py` | MoviePy assembly, aspect ratio conversion |
| **Season** | `seasoning.py` | VO generation, music selection, audio mixing |
| **QC** | `taste_test.py` | ffprobe validation, recipe compliance, preview GIF |

## Recipes

| Recipe | Duration | Aspect | Use Case |
|--------|----------|--------|----------|
| `social_teaser_w24` | 20-30s | 9:16 | Instagram/TikTok teaser |
| `spicy_trailer` | 30-45s | 16:9 | YouTube trailer |
| `highlight_abendsendung` | 60-90s | 16:9 | Broadcast highlight |
| `bts_soup` | 45-60s | 1:1 | Behind the scenes |

## Docker

```bash
docker compose up -d
# → API on http://localhost:3001
```

## Requirements

- Python 3.11+
- Node.js 18+
- ffmpeg (system)
- OpenAI API key (for Whisper transcription + LLM scoring)

## What's New in v0.7.0

- ✅ **Express REST API** — Full CRUD for projects, jobs, outputs, recipes
- ✅ **SQLite Database** — Persistent storage with WAL mode
- ✅ **Job Queue** — In-memory job queue with Python subprocess execution
- ✅ **Web Dashboard** — Dark-themed dashboard for project management
- ✅ **OpenClaw Tools** — `/api/kitchen/tools/*` endpoints for agent integration
- ✅ **Docker Support** — Dockerfile + docker-compose.yml
- ✅ **Python venv** — Isolated dependency management

## License

Proprietary — FFWD Media
