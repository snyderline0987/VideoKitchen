// Video Kitchen v0.8.0 — OpenClaw Agent Integration
// This module registers Video Kitchen as an OpenClaw callable tool

const axios = require('axios');
const path = require('path');
const db = require('./db');
const { enqueueJob } = require('./job-runner');

const API_BASE = process.env.VIDEO_KITCHEN_API_URL || 'http://localhost:3001';
const WEBHOOK_SECRET = process.env.VIDEO_KITCHEN_WEBHOOK_SECRET || 'vk-webhook-secret';

/**
 * Tool definitions for OpenClaw integration
 * These describe the callable operations agents can perform
 */
const TOOL_DEFINITIONS = {
  'video_kitchen_create_project': {
    name: 'video_kitchen_create_project',
    description: 'Create a new video processing project in Video Kitchen',
    parameters: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Project title' },
        source: { type: 'string', description: 'Video file path or URL' },
        source_type: { type: 'string', enum: ['file', 'url', 'w24'], default: 'file' },
        recipe_id: { type: 'string', description: 'Recipe ID (e.g., social_teaser_w24, spicy_trailer)' }
      },
      required: ['title', 'source']
    }
  },
  'video_kitchen_run_pipeline': {
    name: 'video_kitchen_run_pipeline',
    description: 'Run the full video processing pipeline on a project',
    parameters: {
      type: 'object',
      properties: {
        project_id: { type: 'string', description: 'Project ID' },
        recipe_id: { type: 'string', description: 'Recipe to use' },
        auto: { type: 'boolean', default: true, description: 'Run full auto pipeline' },
        vo_text: { type: 'string', description: 'Voice-over text for seasoning' }
      },
      required: ['project_id']
    }
  },
  'video_kitchen_get_status': {
    name: 'video_kitchen_get_status',
    description: 'Get project status, scenes, outputs, and job progress',
    parameters: {
      type: 'object',
      properties: {
        project_id: { type: 'string', description: 'Project ID' },
        job_id: { type: 'string', description: 'Optional: specific job ID' }
      },
      required: ['project_id']
    }
  },
  'video_kitchen_list_outputs': {
    name: 'video_kitchen_list_outputs',
    description: 'List all generated outputs for a project',
    parameters: {
      type: 'object',
      properties: {
        project_id: { type: 'string', description: 'Project ID' }
      },
      required: ['project_id']
    }
  },
  'video_kitchen_process_w24': {
    name: 'video_kitchen_process_w24',
    description: 'Process a W24 news URL automatically',
    parameters: {
      type: 'object',
      properties: {
        w24_url: { type: 'string', description: 'W24 video URL (e.g., https://w24.at/News/...)' },
        recipe_id: { type: 'string', default: 'social_teaser_w24', description: 'Recipe to apply' }
      },
      required: ['w24_url']
    }
  },
  'video_kitchen_dashboard_reply': {
    name: 'video_kitchen_dashboard_reply',
    description: 'Send a rich reply to the Video Kitchen dashboard chat. Supports markdown text, filmstrip scenes, scene cards, output cards, progress bars, and pipeline status.',
    parameters: {
      type: 'object',
      properties: {
        message: { type: 'string', description: 'Message text (markdown supported: **bold**, `code`, [success:text], [error:text], [info:text], [warn:text])' },
        format: { type: 'string', enum: ['text', 'markdown', 'rich'], default: 'rich', description: 'Message format' },
        scenes: { type: 'array', description: 'Filmstrip scenes [{start, end, score, title, project_id}]' },
        scene_card: { type: 'object', description: 'Single scene card {start, end, score, title, thumbnail}' },
        output: { type: 'object', description: 'Output card {id, filename, duration, size}' },
        progress: { type: 'object', description: 'Progress bar {label, percent}' },
        pipeline: { type: 'object', description: 'Pipeline status {current: step_name}' }
      },
      required: ['message']
    }
  }
};

/**
 * Execute a Video Kitchen tool call
 */
async function executeTool(toolName, params) {
  switch (toolName) {
    case 'video_kitchen_create_project':
      return await createProject(params);
    case 'video_kitchen_run_pipeline':
      return await runPipeline(params);
    case 'video_kitchen_get_status':
      return await getStatus(params);
    case 'video_kitchen_list_outputs':
      return await listOutputs(params);
    case 'video_kitchen_process_w24':
      return await processW24(params);
    case 'video_kitchen_dashboard_reply':
      return await dashboardReply(params);
    default:
      throw new Error(`Unknown tool: ${toolName}`);
  }
}

/**
 * Create a new project
 */
async function createProject({ title, source, source_type = 'file', recipe_id }) {
  const { v4: uuidv4 } = require('uuid');
  const id = uuidv4().slice(0, 8);
  
  const project = await db.createProject({
    id,
    title: title || id,
    source,
    source_type,
    status: 'uploaded',
    video_info: {},
    recipe_id
  });

  return {
    success: true,
    project_id: id,
    project,
    message: `Project "${title}" created with ID: ${id}`
  };
}

/**
 * Run the full pipeline on a project
 */
async function runPipeline({ project_id, recipe_id, auto = true, vo_text }) {
  const project = await db.getProject(project_id);
  if (!project) {
    return { success: false, error: `Project ${project_id} not found` };
  }

  const { v4: uuidv4 } = require('uuid');
  const jobId = uuidv4().slice(0, 8);

  const job = await db.createJob({
    id: jobId,
    project_id,
    type: 'auto',
    status: 'queued',
    recipe_id: recipe_id || project.recipe_id,
    params: { vo_text, auto: true }
  });

  // Queue for execution
  enqueueJob(jobId);

  return {
    success: true,
    job_id: jobId,
    project_id,
    status: 'queued',
    message: `Pipeline job ${jobId} queued for project ${project_id}`
  };
}

/**
 * Get project status
 */
async function getStatus({ project_id, job_id }) {
  const project = await db.getProject(project_id);
  if (!project) {
    return { success: false, error: `Project ${project_id} not found` };
  }

  const scenes = await db.loadScenes(project_id);
  const outputs = await db.listOutputs(project_id);
  const jobs = await db.listJobs({ project_id });

  let targetJob = null;
  if (job_id) {
    targetJob = jobs.find(j => j.id === job_id);
  }

  return {
    success: true,
    project: {
      id: project.id,
      title: project.title,
      status: project.status,
      source_type: project.source_type,
      recipe_id: project.recipe_id,
      created_at: project.created_at,
      updated_at: project.updated_at
    },
    scenes_count: scenes.length,
    outputs_count: outputs.length,
    jobs: jobs.map(j => ({
      id: j.id,
      type: j.type,
      status: j.status,
      created_at: j.created_at,
      completed_at: j.completed_at,
      error: j.error
    })),
    job: targetJob ? {
      id: targetJob.id,
      status: targetJob.status,
      logs: targetJob.logs,
      error: targetJob.error,
      started_at: targetJob.started_at,
      completed_at: targetJob.completed_at
    } : null
  };
}

/**
 * List outputs for a project
 */
async function listOutputs({ project_id }) {
  const outputs = await db.listOutputs(project_id);
  
  return {
    success: true,
    project_id,
    outputs: outputs.map(o => ({
      id: o.id,
      filename: o.filename,
      file_size: o.file_size,
      recipe_id: o.recipe_id,
      created_at: o.created_at,
      download_url: `${API_BASE}/api/outputs/${o.id}/download?project_id=${project_id}`
    }))
  };
}

/**
 * Process a W24 URL
 */
async function processW24({ w24_url, recipe_id = 'social_teaser_w24' }) {
  const w24 = require('./w24-handler');
  
  // Validate and extract W24 info
  const w24Info = w24.parseW24Url(w24_url);
  if (!w24Info.valid) {
    return { success: false, error: `Invalid W24 URL: ${w24_url}` };
  }

  // Create project
  const { v4: uuidv4 } = require('uuid');
  const projectId = uuidv4().slice(0, 8);
  
  const project = await db.createProject({
    id: projectId,
    title: `W24: ${w24Info.topic || w24Info.segment}`,
    source: w24_url,
    source_type: 'w24',
    status: 'uploaded',
    video_info: { w24_info: w24Info },
    recipe_id
  });

  // Create and queue job
  const jobId = uuidv4().slice(0, 8);
  const job = await db.createJob({
    id: jobId,
    project_id: projectId,
    type: 'auto',
    status: 'queued',
    recipe_id,
    params: { w24_url, auto: true }
  });

  enqueueJob(jobId);

  return {
    success: true,
    project_id: projectId,
    job_id: jobId,
    w24_info: w24Info,
    status: 'queued',
    message: `W24 project created and pipeline queued. Job ID: ${jobId}`
  };
}

/**
 * Webhook handler for job completion callbacks
 */
async function handleWebhook(payload, signature) {
  // Verify signature (basic HMAC check)
  const crypto = require('crypto');
  const expected = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(JSON.stringify(payload))
    .digest('hex');
  
  if (signature !== expected) {
    throw new Error('Invalid webhook signature');
  }

  const { job_id, status, outputs } = payload;
  
  // Update job status
  await db.updateJob(job_id, {
    status,
    completed_at: new Date().toISOString()
  });

  // Sync any new outputs
  if (outputs && outputs.length > 0) {
    for (const output of outputs) {
      await db.saveOutput(output);
    }
  }

  return { received: true, job_id, status };
}

/**
 * Send a rich reply to the Video Kitchen dashboard chat
 */
async function dashboardReply({ message, format = 'rich', scenes, scene_card, output, progress, pipeline }) {
  const { v4: uuidv4 } = require('uuid');
  const metadata = {};
  if (scenes) metadata.scenes = scenes;
  if (scene_card) metadata.scene_card = scene_card;
  if (output) metadata.output = output;
  if (progress) metadata.progress = progress;
  if (pipeline) metadata.pipeline = pipeline;
  if (Object.keys(metadata).length > 0) metadata.text = message;

  try {
    const res = await axios.post(`${API_BASE}/api/chat`, {
      role: 'assistant',
      content: message,
      format,
      ...(Object.keys(metadata).length > 0 ? { metadata } : {})
    });
    return { success: true, message_id: res.data?.id, format };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

module.exports = {
  TOOL_DEFINITIONS,
  executeTool,
  handleWebhook,
  createProject,
  runPipeline,
  getStatus,
  listOutputs,
  processW24,
  dashboardReply
};
