const sqlite3 = require('sqlite3').verbose();
const { open } = require('sqlite');
const path = require('path');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, 'data', 'video_kitchen.db');

let dbInstance = null;

async function getDb() {
  if (!dbInstance) {
    dbInstance = await open({
      filename: DB_PATH,
      driver: sqlite3.Database
    });
    await dbInstance.run('PRAGMA journal_mode = WAL');
    await dbInstance.run('PRAGMA foreign_keys = ON');
  }
  return dbInstance;
}

// Project operations
async function createProject(project) {
  const db = await getDb();
  const { id, title, source, source_type, status, video_info, recipe_id } = project;
  await db.run(
    `INSERT INTO projects (id, title, source, source_type, status, video_info, scene_count, recipe_id)
     VALUES (?, ?, ?, ?, ?, ?, 0, ?)`,
    [id, title, source, source_type || 'file', status || 'uploaded', JSON.stringify(video_info || {}), recipe_id || null]
  );
  return project;
}

async function getProject(id) {
  const db = await getDb();
  const project = await db.get('SELECT * FROM projects WHERE id = ?', id);
  if (project) {
    project.video_info = JSON.parse(project.video_info || '{}');
  }
  return project;
}

async function listProjects() {
  const db = await getDb();
  const projects = await db.all('SELECT * FROM projects ORDER BY created_at DESC');
  return projects.map(p => ({ ...p, video_info: JSON.parse(p.video_info || '{}') }));
}

async function updateProject(id, updates) {
  const db = await getDb();
  const fields = [];
  const values = [];
  for (const [key, value] of Object.entries(updates)) {
    if (key === 'video_info') {
      fields.push(`${key} = ?`);
      values.push(JSON.stringify(value));
    } else {
      fields.push(`${key} = ?`);
      values.push(value);
    }
  }
  fields.push('updated_at = CURRENT_TIMESTAMP');
  values.push(id);
  await db.run(`UPDATE projects SET ${fields.join(', ')} WHERE id = ?`, values);
  return getProject(id);
}

async function deleteProject(id) {
  const db = await getDb();
  await db.run('DELETE FROM projects WHERE id = ?', id);
}

// Scene operations
async function saveScenes(projectId, scenes) {
  const db = await getDb();
  const insert = await db.prepare(`
    INSERT OR REPLACE INTO scenes 
    (id, project_id, scene_index, start_time, end_time, duration, thumbnail,
     visual_score, transcript_score, audio_score, combined_score, transcript, labels, selected)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  for (const scene of scenes) {
    await insert.run(
      scene.id || `${projectId}_${scene.scene_index}`,
      projectId,
      scene.scene_index,
      scene.start_time,
      scene.end_time,
      scene.duration,
      scene.thumbnail,
      scene.visual_score,
      scene.transcript_score,
      scene.audio_score,
      scene.combined_score,
      scene.transcript,
      JSON.stringify(scene.labels || []),
      scene.selected || false
    );
  }
  await insert.finalize();
  await db.run('UPDATE projects SET scene_count = ? WHERE id = ?', [scenes.length, projectId]);
}

async function loadScenes(projectId) {
  const db = await getDb();
  const scenes = await db.all('SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_index', projectId);
  return scenes.map(s => ({ ...s, labels: JSON.parse(s.labels || '[]') }));
}

// Job operations
async function createJob(job) {
  const db = await getDb();
  const { id, project_id, type, status, recipe_id, params } = job;
  await db.run(
    `INSERT INTO jobs (id, project_id, type, status, recipe_id, params)
     VALUES (?, ?, ?, ?, ?, ?)`,
    [id, project_id, type, status || 'queued', recipe_id || null, JSON.stringify(params || {})]
  );
  return job;
}

async function getJob(id) {
  const db = await getDb();
  const job = await db.get('SELECT * FROM jobs WHERE id = ?', id);
  if (job) {
    job.params = JSON.parse(job.params || '{}');
  }
  return job;
}

async function listJobs(filters = {}) {
  const db = await getDb();
  let query = 'SELECT * FROM jobs';
  const conditions = [];
  const values = [];
  if (filters.project_id) {
    conditions.push('project_id = ?');
    values.push(filters.project_id);
  }
  if (filters.status) {
    conditions.push('status = ?');
    values.push(filters.status);
  }
  if (conditions.length) {
    query += ' WHERE ' + conditions.join(' AND ');
  }
  query += ' ORDER BY created_at DESC';
  const jobs = await db.all(query, values);
  return jobs.map(j => ({ ...j, params: JSON.parse(j.params || '{}') }));
}

async function updateJob(id, updates) {
  const db = await getDb();
  const fields = [];
  const values = [];
  for (const [key, value] of Object.entries(updates)) {
    if (key === 'params') {
      fields.push(`${key} = ?`);
      values.push(JSON.stringify(value));
    } else {
      fields.push(`${key} = ?`);
      values.push(value);
    }
  }
  values.push(id);
  await db.run(`UPDATE jobs SET ${fields.join(', ')} WHERE id = ?`, values);
  return getJob(id);
}

// Output operations
async function saveOutput(output) {
  const db = await getDb();
  const { id, project_id, job_id, recipe_id, filename, file_path, duration, resolution, file_size, qc_passed, qc_report, preview_path } = output;
  await db.run(
    `INSERT INTO outputs (id, project_id, job_id, recipe_id, filename, file_path, duration, resolution, file_size, qc_passed, qc_report, preview_path)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [id, project_id, job_id, recipe_id, filename, file_path, duration, resolution, file_size, qc_passed, JSON.stringify(qc_report || {}), preview_path]
  );
  return output;
}

async function listOutputs(projectId) {
  const db = await getDb();
  const outputs = await db.all('SELECT * FROM outputs WHERE project_id = ? ORDER BY created_at DESC', projectId);
  return outputs.map(o => ({ ...o, qc_report: JSON.parse(o.qc_report || '{}') }));
}

// Recipe operations
async function listRecipes() {
  const db = await getDb();
  const recipes = await db.all('SELECT * FROM recipes ORDER BY name');
  return recipes.map(r => ({ ...r, config: JSON.parse(r.config) }));
}

async function getRecipe(id) {
  const db = await getDb();
  const recipe = await db.get('SELECT * FROM recipes WHERE id = ?', id);
  if (recipe) {
    recipe.config = JSON.parse(recipe.config);
  }
  return recipe;
}

module.exports = {
  getDb,
  createProject,
  getProject,
  listProjects,
  updateProject,
  deleteProject,
  saveScenes,
  loadScenes,
  createJob,
  getJob,
  listJobs,
  updateJob,
  saveOutput,
  listOutputs,
  listRecipes,
  getRecipe
};
