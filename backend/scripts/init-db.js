const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

const DB_DIR = path.join(__dirname, '..', 'data');
const DB_PATH = process.env.DB_PATH || path.join(DB_DIR, 'video_kitchen.db');

// Ensure data directory exists
if (!fs.existsSync(DB_DIR)) {
  fs.mkdirSync(DB_DIR, { recursive: true });
}

const db = new sqlite3.Database(DB_PATH);

// Enable WAL mode for better concurrency
db.run('PRAGMA journal_mode = WAL;');
db.run('PRAGMA foreign_keys = ON;');

// Initialize schema
const initSchema = () => {
  db.exec(`
    -- Projects table
    CREATE TABLE IF NOT EXISTS projects (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      source TEXT,
      source_type TEXT DEFAULT 'file',
      status TEXT DEFAULT 'uploaded',
      video_info TEXT,
      scene_count INTEGER DEFAULT 0,
      recipe_id TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Scenes table
    CREATE TABLE IF NOT EXISTS scenes (
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
      labels TEXT,
      selected BOOLEAN DEFAULT FALSE,
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- Jobs table
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      type TEXT NOT NULL,
      status TEXT DEFAULT 'queued',
      recipe_id TEXT,
      params TEXT,
      logs TEXT,
      error TEXT,
      started_at DATETIME,
      completed_at DATETIME,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- Outputs table
    CREATE TABLE IF NOT EXISTS outputs (
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
      qc_report TEXT,
      preview_path TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
      FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
    );

    -- Recipes table
    CREATE TABLE IF NOT EXISTS recipes (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      config TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id);
    CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    CREATE INDEX IF NOT EXISTS idx_outputs_project ON outputs(project_id);
  `, (err) => {
    if (err) {
      console.error('Schema init error:', err);
      process.exit(1);
    }
    console.log('Database initialized at', DB_PATH);
    process.exit(0);
  });
};

initSchema();
