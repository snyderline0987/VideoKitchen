const express = require('express');
const cors = require('cors');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const fs = require('fs');

const db = require('./db');
const { enqueueJob, runJob } = require('./job-runner');
const openclawTools = require('./openclaw-tools');
const w24Handler = require('./w24-handler');
const zaiVision = require('./zai-vision-mcp');
const hardening = require('./production-hardening');

const app = express();
const PORT = process.env.PORT || 3001;
const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');

// Ensure projects directory exists
if (!fs.existsSync(PROJECTS_DIR)) {
  fs.mkdirSync(PROJECTS_DIR, { recursive: true });
}

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'dashboard')));

// ─── Health ───────────────────────────────────────────────────────

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', version: '0.8.0', phase: '3', timestamp: new Date().toISOString() });
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

// ─── OpenClaw Agent Tools ─────────────────────────────────────────

app.post('/api/tools/:tool', async (req, res) => {
  try {
    const tool = req.params.tool;
    const params = req.body;
    
    const result = await openclawTools.executeTool(tool, params);
    res.json(result);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.get('/api/tools', (req, res) => {
  res.json({
    tools: Object.keys(openclawTools.TOOL_DEFINITIONS).map(key => ({
      name: key,
      ...openclawTools.TOOL_DEFINITIONS[key]
    }))
  });
});

// ─── Webhook Callbacks ────────────────────────────────────────────

app.post('/api/webhooks/job-complete', async (req, res) => {
  try {
    const signature = req.headers['x-webhook-signature'];
    const result = await openclawTools.handleWebhook(req.body, signature);
    res.json(result);
  } catch (err) {
    res.status(401).json({ error: err.message });
  }
});

// ─── W24 Integration ────────────────────────────────────────────

app.post('/api/w24/parse', (req, res) => {
  try {
    const { url } = req.body;
    const info = w24Handler.parseW24Url(url);
    res.json(info);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/w24/download', async (req, res) => {
  try {
    const { url, output_dir } = req.body;
    const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');
    const dir = output_dir || path.join(PROJECTS_DIR, 'w24-downloads');
    
    const result = await w24Handler.downloadW24Video(url, dir);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/w24/metadata', async (req, res) => {
  try {
    const { url } = req.body;
    const result = await w24Handler.getW24Metadata(url);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── zai-vision Integration ───────────────────────────────────────

app.post('/api/vision/analyze', async (req, res) => {
  try {
    const { video_path, options } = req.body;
    const result = await zaiVision.analyzeVideo(video_path, options);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/vision/feed-scoring', async (req, res) => {
  try {
    const { project_id, analysis } = req.body;
    const result = await zaiVision.feedIntoScoring(project_id, analysis);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Progress Streaming (SSE) ─────────────────────────────────────

app.get('/api/jobs/:id/progress', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  
  const jobId = req.params.id;
  
  const sendProgress = (update) => {
    if (update.job_id === jobId) {
      res.write(`data: ${JSON.stringify(update)}\n\n`);
    }
  };
  
  hardening.progressEmitter.on('progress', sendProgress);
  
  req.on('close', () => {
    hardening.progressEmitter.off('progress', sendProgress);
  });
});

// ─── Output Gallery ───────────────────────────────────────────────

app.get('/api/projects/:id/gallery', async (req, res) => {
  try {
    const gallery = await hardening.getOutputGallery(req.params.id);
    res.json(gallery);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Cleanup ──────────────────────────────────────────────────────

app.post('/api/projects/:id/cleanup', async (req, res) => {
  try {
    const result = await hardening.cleanupProject(req.params.id, req.body);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/admin/cleanup-all', async (req, res) => {
  try {
    const result = await hardening.cleanupOldTempFiles();
    res.json(result);
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

// ─── Chat (Agent ↔ Dashboard Bridge) ────────────────────────────────

// Create chat_messages table
async function ensureChatTable() {
  const dbConn = await db.getDb();
  await dbConn.run(`CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    format TEXT DEFAULT 'text',
    metadata TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);
}
ensureChatTable();

// SSE for live chat
const chatClients = new Set();
function broadcastChat(msg) {
  const data = JSON.stringify(msg);
  chatClients.forEach(client => client.write(`data: ${data}\n\n`));
}

app.get('/api/chat/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();
  chatClients.add(res);
  req.on('close', () => chatClients.delete(res));
});

app.get('/api/chat', async (req, res) => {
  try {
    const dbConn = await db.getDb();
    const msgs = await dbConn.all(
      'SELECT * FROM chat_messages ORDER BY created_at ASC LIMIT 100'
    );
    res.json(msgs);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/chat', async (req, res) => {
  try {
    const { role, content, format, metadata } = req.body;
    if (!role || !content) return res.status(400).json({ error: 'role and content required' });
    const id = uuidv4();
    const dbConn = await db.getDb();
    await dbConn.run(
      'INSERT INTO chat_messages (id, role, content, format, metadata) VALUES (?, ?, ?, ?, ?)',
      [id, role, content, format || 'text', metadata ? JSON.stringify(metadata) : null]
    );
    const msg = { id, role, content, format: format || 'text', metadata: metadata || null, created_at: new Date().toISOString() };
    broadcastChat(msg);
    res.json(msg);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete('/api/chat', async (req, res) => {
  try {
    const dbConn = await db.getDb();
    await dbConn.run('DELETE FROM chat_messages');
    broadcastChat({ type: 'cleared' });
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Agent chat tool: dashboard messages → agent reads, agent responds
app.post('/api/tools/video_kitchen_agent_chat', async (req, res) => {
  try {
    const { message } = req.body;
    if (!message) return res.status(400).json({ error: 'message required' });
    // Store user message
    await (async () => {
      const id = uuidv4();
      const dbConn = await db.getDb();
      await dbConn.run('INSERT INTO chat_messages (id, role, content, format) VALUES (?, ?, ?, ?)',
        [id, 'user', message, 'text']);
      broadcastChat({ id, role: 'user', content: message, format: 'text', created_at: new Date().toISOString() });
    })();
    // Return a placeholder — agent will respond via POST /api/chat
    res.json({ success: true, message: 'Message sent to agent' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── Start ────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`Video Kitchen API v0.8.0 running on http://localhost:${PORT}`);
  console.log(`Phase 3: Agent Integration enabled`);
  console.log(`Projects dir: ${PROJECTS_DIR}`);
});

module.exports = app;
