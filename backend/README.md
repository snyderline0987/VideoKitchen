# Video Kitchen — Phase 2 Backend API

## Overview

Phase 2 adds an Express.js REST API + SQLite database layer on top of the existing Python pipeline. This enables:
- Web dashboard integration
- Job queue management
- Agentic control via OpenClaw tools
- Project lifecycle management

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Video Kitchen v0.7.0                     │
├─────────────────────────────────────────────────────────────┤
│  Web Dashboard (Next.js)  │  OpenClaw Agent  │  CLI (legacy) │
├─────────────────────────────────────────────────────────────┤
│                    Express REST API (Node.js)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /projects   │  │ /jobs       │  │ /kitchen/tools        │  │
│  │ CRUD        │  │ Queue/Run   │  │ OpenClaw integration  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    SQLite Database                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ projects    │  │ jobs        │  │ outputs             │  │
│  │ scenes      │  │ transcripts │  │ recipes             │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Python Pipeline Engine                      │
│  prep_station → scoring → select → plate → season → qc       │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoints

### Projects
- `GET /api/projects` — List all projects
- `POST /api/projects` — Create project (upload video URL or file)
- `GET /api/projects/:id` — Get project with scenes, outputs
- `PATCH /api/projects/:id` — Update project status/metadata
- `DELETE /api/projects/:id` — Delete project

### Jobs
- `GET /api/jobs` — List jobs (filter by project, status)
- `POST /api/jobs` — Create job (pipeline stage)
- `GET /api/jobs/:id` — Get job status + logs
- `POST /api/jobs/:id/run` — Execute job (spawns Python process)
- `PATCH /api/jobs/:id` — Update job status

### Kitchen Tools (OpenClaw Integration)
- `POST /api/kitchen/tools/detect-scenes` — Run scene detection
- `POST /api/kitchen/tools/score` — Run AI scoring
- `POST /api/kitchen/tools/plate` — Assemble video
- `POST /api/kitchen/tools/season` — Add audio
- `POST /api/kitchen/tools/qc` — Quality check
- `POST /api/kitchen/tools/auto` — Full auto pipeline

### Outputs
- `GET /api/outputs` — List rendered outputs
- `GET /api/outputs/:id/download` — Download output file
- `GET /api/outputs/:id/preview` — Get preview GIF

## Database Schema

```sql
-- Projects table
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT,
    source_type TEXT DEFAULT 'file',
    status TEXT DEFAULT 'uploaded',
    video_info JSON,
    scene_count INTEGER DEFAULT 0,
    recipe_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Scenes table (normalized from scenes.json)
CREATE TABLE scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_index INTEGER NOT NULL,
    start_time REAL,
    end_time REAL,
    duration REAL,
    thumbnail TEXT,
    visual_score REAL,
    transcript_score REAL,
    audio_score REAL,
    combined_score REAL,
    transcript TEXT,
    labels JSON,
    selected BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Jobs table (pipeline execution tracking)
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type TEXT NOT NULL, -- 'prep', 'analyze', 'select', 'plate', 'season', 'qc', 'auto'
    status TEXT DEFAULT 'queued', -- 'queued', 'running', 'done', 'failed', 'cancelled'
    recipe_id TEXT,
    params JSON,
    logs TEXT,
    error TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Outputs table
CREATE TABLE outputs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_id TEXT,
    recipe_id TEXT,
    filename TEXT,
    file_path TEXT,
    duration REAL,
    resolution TEXT,
    file_size INTEGER,
    qc_passed BOOLEAN,
    qc_report JSON,
    preview_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

-- Recipes table (recipe registry)
CREATE TABLE recipes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Job Execution Flow

1. **Create Job** — `POST /api/jobs` with project_id, type, recipe, params
2. **Queue** — Job status = `queued`, added to in-memory queue
3. **Run** — `POST /api/jobs/:id/run` or auto-pick from queue
4. **Execute** — Spawn Python subprocess via `child_process.spawn()`
   ```javascript
   const proc = spawn('python3', [
     'scripts/kitchen.py',
     '--project', projectId,
     '--recipe', recipeId,
     recipeId === 'auto' ? '--auto' : `--${jobType}`
   ], { cwd: '/path/to/video-kitchen' });
   ```
5. **Stream Logs** — Capture stdout/stderr, update job.logs
6. **Complete** — On exit code 0, status = `done`; else `failed`
7. **Sync** — Read output files, update database records

## OpenClaw Tool Integration

The API exposes endpoints that map directly to OpenClaw tools:

```javascript
// Example: Agent calls POST /api/kitchen/tools/auto
// with body: { projectId, recipeId, videoUrl }
// The API creates a job, runs the pipeline, returns jobId

// Agent can poll GET /api/jobs/:id for status
// Or receive webhook on completion
```

## Getting Started

```bash
# 1. Install dependencies
cd backend
npm install

# 2. Initialize database
npm run db:init

# 3. Seed recipes
npm run db:seed

# 4. Start server
npm start
# Server runs on http://localhost:3001

# 5. Test API
curl http://localhost:3001/api/health
```

## Environment Variables

```bash
PORT=3001
DB_PATH=./data/video_kitchen.db
PROJECTS_BASE_DIR=./projects
PYTHON_PATH=python3
KITCHEN_SCRIPTS_DIR=../scripts
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=sk-...
```

## Phase 2 Checklist

- [x] Review Phase 1 codebase
- [ ] Express API scaffold
- [ ] SQLite schema + migrations
- [ ] Project CRUD endpoints
- [ ] Job queue system
- [ ] Python pipeline integration (spawn)
- [ ] Recipe registry (DB + endpoints)
- [ ] Output serving (download, preview)
- [ ] OpenClaw tool endpoints
- [ ] WebSocket for job progress
- [ ] Error handling + retries
- [ ] Tests

## Next: Phase 3

Phase 3 (Web Dashboard) will consume this API:
- Next.js frontend
- Project gallery
- Scene browser with thumbnails
- Recipe picker
- Job progress UI
- Output preview + download
