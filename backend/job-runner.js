const { spawn } = require('child_process');
const path = require('path');
const db = require('./db');
const hardening = require('./production-hardening');

const PROJECTS_DIR = process.env.PROJECTS_BASE_DIR || path.join(__dirname, '..', 'projects');
const SCRIPTS_DIR = process.env.KITCHEN_SCRIPTS_DIR || path.join(__dirname, '..', 'scripts');
const fs = require('fs');
const PYTHON_PATH = process.env.PYTHON_PATH || path.join(__dirname, '..', '.venv', 'bin', 'python3');

// In-memory job queue
const jobQueue = [];
let isProcessing = false;

async function enqueueJob(jobId) {
  const job = await db.getJob(jobId);
  if (!job) return;
  
  jobQueue.push(job);
  console.log(`[QUEUE] Job ${jobId} enqueued. Queue length: ${jobQueue.length}`);
  
  if (!isProcessing) {
    processQueue();
  }
}

async function processQueue() {
  if (isProcessing || jobQueue.length === 0) return;
  
  isProcessing = true;
  const job = jobQueue.shift();
  
  try {
    // Use retry logic for production hardening
    await hardening.runWithRetry(job.id, async () => {
      await runJob(job);
    });
  } catch (err) {
    console.error(`[QUEUE] Job ${job.id} failed after retries:`, err.message);
  } finally {
    isProcessing = false;
    // Process next if available
    if (jobQueue.length > 0) {
      setImmediate(processQueue);
    }
  }
}

async function runJob(job) {
  const project = await db.getProject(job.project_id);
  if (!project) throw new Error('Project not found');

  // Update status to running
  await db.updateJob(job.id, { 
    status: 'running', 
    started_at: new Date().toISOString(),
    logs: '' 
  });

  // Download URL sources before pipeline
  let sourcePath = project.source;
  if (sourcePath && sourcePath.startsWith('http')) {
    const projectDir = path.join(PROJECTS_DIR, job.project_id);
    if (!fs.existsSync(projectDir)) fs.mkdirSync(projectDir, { recursive: true });
    const localFile = path.join(projectDir, 'source.mp4');
    if (!fs.existsSync(localFile)) {
      console.log(`[JOB ${job.id}] Downloading: ${sourcePath}`);
      const { execSync } = require('child_process');
      execSync(`curl -sL -o "${localFile}" "${sourcePath}"`, { timeout: 300000 });
      console.log(`[JOB ${job.id}] Downloaded to: ${localFile}`);
    }
    sourcePath = localFile;
    // Update project source to local file
    const dbConn = await db.getDb();
    await dbConn.run('UPDATE projects SET source = ? WHERE id = ?', [localFile, job.project_id]);
  }

  // Build command
  const args = ['kitchen.py', '--project', job.project_id, '--base-dir', PROJECTS_DIR];
  
  if (job.type === 'auto') {
    args.push('--auto');
    if (job.recipe_id) args.push('--recipe', job.recipe_id);
    if (sourcePath) args.push('--open', sourcePath);
  } else if (job.type === 'prep') {
    args.push('--open', sourcePath);
    args.push('--transcribe');
  } else {
    args.push(`--${job.type}`);
    if (job.recipe_id) args.push('--recipe', job.recipe_id);
  }

  // Add extra params
  let params = job.params;
  if (typeof params === 'string') {
    try { params = JSON.parse(params); } catch (e) { params = {}; }
  }
  if (params) {
    if (params.vo_text) args.push('--vo-text', params.vo_text);
    if (params.threshold) args.push('--threshold', String(params.threshold));
    if (params.min_scene_len) args.push('--min-scene-len', String(params.min_scene_len));
    if (params.top) args.push('--top', String(params.top));
    if (params.weights) args.push('--weights', params.weights);
  }

  const cmdStr = `${PYTHON_PATH} ${args.join(' ')}`;
  console.log(`[JOB ${job.id}] Running: ${cmdStr}`);

  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON_PATH, args, {
      cwd: SCRIPTS_DIR,
      env: { ...process.env, PYTHONPATH: SCRIPTS_DIR }
    });

    let logs = '';
    proc.stdout.on('data', async (data) => {
      const chunk = data.toString();
      logs += chunk;
      console.log(`[JOB ${job.id}] ${chunk.trim()}`);
      
      // Parse progress from output and report
      const progressMatch = chunk.match(/Progress: (\d+)%/);
      if (progressMatch) {
        const progress = parseInt(progressMatch[1]);
        await hardening.reportProgress(job.id, job.type, progress, chunk.trim());
      }
    });
    proc.stderr.on('data', (data) => {
      const chunk = data.toString();
      logs += chunk;
      console.error(`[JOB ${job.id}] ${chunk.trim()}`);
    });

    proc.on('close', async (code) => {
      const status = code === 0 ? 'done' : 'failed';
      const error = code !== 0 ? `Process exited with code ${code}` : null;
      
      await db.updateJob(job.id, {
        status,
        logs,
        error,
        completed_at: new Date().toISOString()
      });

      // Sync outputs
      await syncOutputs(job);
      
      // Generate thumbnails for new outputs
      const outputsDir = path.join(PROJECTS_DIR, job.project_id, 'outputs');
      if (fs.existsSync(outputsDir)) {
        const files = fs.readdirSync(outputsDir).filter(f => f.endsWith('.mp4'));
        for (const file of files) {
          const filePath = path.join(outputsDir, file);
          await hardening.generateThumbnail(filePath, outputsDir);
          await hardening.generatePreviewGif(filePath, outputsDir);
        }
      }
      
      // Report final progress
      await hardening.reportProgress(job.id, job.type, code === 0 ? 100 : 0, 
        code === 0 ? 'Completed successfully' : `Failed with code ${code}`);

      console.log(`[JOB ${job.id}] Completed with status: ${status}`);
      
      if (code === 0) {
        resolve({ status, logs });
      } else {
        reject(new Error(error));
      }
    });

    proc.on('error', async (err) => {
      await db.updateJob(job.id, {
        status: 'failed',
        logs,
        error: err.message,
        completed_at: new Date().toISOString()
      });
      reject(err);
    });
  });
}

async function syncOutputs(job) {
  const fs = require('fs');
  const { v4: uuidv4 } = require('uuid');
  
  const outputsDir = path.join(PROJECTS_DIR, job.project_id, 'outputs');
  if (!fs.existsSync(outputsDir)) return;

  const files = fs.readdirSync(outputsDir);
  const existing = await db.listOutputs(job.project_id);
  
  for (const file of files.filter(f => f.endsWith('.mp4') && !f.includes('preview'))) {
    if (existing.some(o => o.filename === file)) continue;
    
    const filePath = path.join(outputsDir, file);
    const stats = fs.statSync(filePath);
    
    await db.saveOutput({
      id: uuidv4().slice(0, 8),
      project_id: job.project_id,
      job_id: job.id,
      recipe_id: job.recipe_id,
      filename: file,
      file_path: filePath,
      file_size: stats.size
    });
  }
}

module.exports = {
  enqueueJob,
  runJob,
  syncOutputs
};
