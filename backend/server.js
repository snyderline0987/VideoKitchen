const express = require('express');
const cors = require('cors');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const fs = require('fs');

const db = require('./db');
const { enqueueJob, runJob } = require('./job-runner');

const app = express();
const PORT = process.env.PORT || 3001;
const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');

// Ensure projects directory exists
if (!fs.existsSync(PROJECTS_DIR)) {
  fs.mkdirSync(PROJECTS_DIR, { recursive: true });
}

app.use(cors());
app.use(express.json());

// ─── Health ───────────────────────────────────────────────────────

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', version: '0.7.0', timestamp: new Date().toISOString() });
});

// ─── Projects ───────────────────────────────────────────────────────

app.get('/api/projects', async (req, res) => {
  try {
    const projects = await db.listProjects();
    res.json(projects);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/projects', async (req, res) => {
  try {
    const { title, source, source_type, recipe_id } = req.body;
    const id = uuidv4().slice(0, 8);
    const project = await db.createProject({
      id,
      title: title || id,
      source,
      source_type: source_type || 'file',
      status: 'uploaded',
      video_info: {},
      recipe_id
    });
    res.status(201).json(project);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/projects/:id', async (req, res) => {
  try {
    const project = await db.getProject(req.params.id);
    if (!project) return res.status(404).json({ error: 'Project not found' });
    const scenes = await db.loadScenes(req.params.id);
    const outputs = await db.listOutputs(req.params.id);
    const jobs = await db.listJobs({ project_id: req.params.id });
    res.json({ ...project, scenes, outputs, jobs });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.patch('/api/projects/:id', async (req, res) => {
  try {
    const project = await db.updateProject(req.params.id, req.body);
    res.json(project);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete('/api/projects/:id', async (req, res) => {
  try {
    await db.deleteProject(req.params.id);
    // Clean up project directory
    const projectDir = path.join(PROJECTS_DIR, req.params.id);
    if (fs.existsSync(projectDir)) {
      fs.rmSync(projectDir, { recursive: true });
    }
    res.json({ deleted: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Jobs ─────────────────────────────────────────────────────────

app.get('/api/jobs', async (req, res) => {
  try {
    const filters = {};
    if (req.query.project_id) filters.project_id = req.query.project_id;
    if (req.query.status) filters.status = req.query.status;
    const jobs = await db.listJobs(filters);
    res.json(jobs);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/jobs', async (req, res) => {
  try {
    const { project_id, type, recipe_id, params } = req.body;
    const id = uuidv4().slice(0, 8);
    const job = await db.createJob({
      id,
      project_id,
      type,
      status: 'queued',
      recipe_id,
      params: params || {}
    });
    res.status(201).json(job);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/jobs/:id', async (req, res) => {
  try {
    const job = await db.getJob(req.params.id);
    if (!job) return res.status(404).json({ error: 'Job not found' });
    res.json(job);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/jobs/:id/run', async (req, res) => {
  try {
    const job = await db.getJob(req.params.id);
    if (!job) return res.status(404).json({ error: 'Job not found' });
    if (job.status === 'running') return res.status(409).json({ error: 'Job already running' });

    // Queue the job for execution
    enqueueJob(req.params.id);

    res.json({ id: req.params.id, status: 'queued_for_run', message: 'Job queued for execution' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.patch('/api/jobs/:id', async (req, res) => {
  try {
    const job = await db.updateJob(req.params.id, req.body);
    res.json(job);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Kitchen Tools (OpenClaw Integration) ─────────────────────────

app.post('/api/kitchen/tools/:tool', async (req, res) => {
  try {
    const { project_id, recipe_id, params } = req.body;
    const tool = req.params.tool;

    const validTools = ['detect-scenes', 'score', 'plate', 'season', 'qc', 'auto'];
    if (!validTools.includes(tool)) {
      return res.status(400).json({ error: `Unknown tool: ${tool}. Valid: ${validTools.join(', ')}` });
    }

    // Map tool names to job types
    const toolToType = {
      'detect-scenes': 'prep',
      'score': 'analyze',
      'plate': 'plate',
      'season': 'season',
      'qc': 'qc',
      'auto': 'auto'
    };

    const job = await db.createJob({
      id: uuidv4().slice(0, 8),
      project_id,
      type: toolToType[tool],
      status: 'queued',
      recipe_id,
      params: params || {}
    });

    res.status(201).json({ job_id: job.id, status: 'queued', tool });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Outputs ──────────────────────────────────────────────────────

app.get('/api/outputs', async (req, res) => {
  try {
    if (req.query.project_id) {
      const outputs = await db.listOutputs(req.query.project_id);
      res.json(outputs);
    } else {
      res.status(400).json({ error: 'project_id required' });
    }
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/outputs/:id/download', async (req, res) => {
  try {
    // Find output by id
    const outputs = await db.listOutputs(req.query.project_id);
    const output = outputs.find(o => o.id === req.params.id);
    if (!output || !fs.existsSync(output.file_path)) {
      return res.status(404).json({ error: 'Output not found' });
    }
    res.download(output.file_path, output.filename);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Recipes ──────────────────────────────────────────────────────

app.get('/api/recipes', async (req, res) => {
  try {
    const recipes = await db.listRecipes();
    res.json(recipes);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/recipes/:id', async (req, res) => {
  try {
    const recipe = await db.getRecipe(req.params.id);
    if (!recipe) return res.status(404).json({ error: 'Recipe not found' });
    res.json(recipe);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Start ────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`Video Kitchen API v0.7.0 running on http://localhost:${PORT}`);
  console.log(`Projects dir: ${PROJECTS_DIR}`);
});

module.exports = app;
