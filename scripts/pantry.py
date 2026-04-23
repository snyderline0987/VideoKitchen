#!/usr/bin/env python3
"""
pantry.py — Metadata Storage for Video Kitchen v0.6.0

The pantry stores all project metadata: scenes, scores, transcripts, and outputs.
Uses a JSON-based file store with project-level isolation.

Usage:
    from pantry import Pantry
    pantry = Pantry(base_dir="/path/to/projects")
    pantry.create_project("my_project", source="video.mp4")
    pantry.save_scenes("my_project", scenes_list)
    scenes = pantry.load_scenes("my_project")
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class Pantry:
    """Project metadata store — the Kitchen's pantry."""

    def __init__(self, base_dir: str = "./projects"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self.base_dir / project_id

    def _ensure_project(self, project_id: str) -> Path:
        pdir = self._project_dir(project_id)
        if not pdir.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        return pdir

    def _read_json(self, path: Path, default: Any = None) -> Any:
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return default

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=self._json_default)

    @staticmethod
    def _json_default(obj):
        """Handle non-serializable types (numpy, etc)."""
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    # ─── Project CRUD ──────────────────────────────────────

    def create_project(
        self,
        project_id: Optional[str] = None,
        title: str = "Untitled",
        source: str = "",
        source_type: str = "file",
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a new project with directory structure."""
        if project_id is None:
            project_id = str(uuid.uuid4())[:8]

        pdir = self._project_dir(project_id)
        if pdir.exists():
            raise FileExistsError(f"Project already exists: {project_id}")

        # Create directory structure
        (pdir / "scenes").mkdir(parents=True)
        (pdir / "thumbnails").mkdir(parents=True)
        (pdir / "outputs").mkdir(parents=True)

        project_meta = {
            "id": project_id,
            "title": title,
            "source": source,
            "source_type": source_type,
            "status": "uploaded",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._write_json(pdir / "project.json", project_meta)
        return project_meta

    def get_project(self, project_id: str) -> dict:
        """Read project metadata."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "project.json")

    def update_project(self, project_id: str, updates: dict) -> dict:
        """Update project metadata fields."""
        pdir = self._ensure_project(project_id)
        meta = self._read_json(pdir / "project.json")
        meta.update(updates)
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(pdir / "project.json", meta)
        return meta

    def delete_project(self, project_id: str) -> None:
        """Delete a project and all its data."""
        pdir = self._project_dir(project_id)
        if pdir.exists():
            shutil.rmtree(pdir)

    def list_projects(self) -> list[dict]:
        """List all projects."""
        projects = []
        for pdir in sorted(self.base_dir.iterdir()):
            meta_path = pdir / "project.json"
            if meta_path.exists():
                projects.append(self._read_json(meta_path))
        return projects

    # ─── Scenes ────────────────────────────────────────────

    def save_scenes(self, project_id: str, scenes: list[dict]) -> None:
        """Save detected scenes (replaces existing)."""
        pdir = self._ensure_project(project_id)
        self._write_json(pdir / "scenes.json", scenes)

    def load_scenes(self, project_id: str) -> list[dict]:
        """Load scenes for a project."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "scenes.json", [])

    def update_scene(self, project_id: str, scene_index: int, updates: dict) -> dict:
        """Update a single scene by index."""
        scenes = self.load_scenes(project_id)
        if scene_index < 0 or scene_index >= len(scenes):
            raise IndexError(f"Scene index out of range: {scene_index}")
        scenes[scene_index].update(updates)
        self.save_scenes(project_id, scenes)
        return scenes[scene_index]

    # ─── Selection ─────────────────────────────────────────

    def save_selection(self, project_id: str, selection: dict) -> None:
        """Save scene selection for plating."""
        pdir = self._ensure_project(project_id)
        self._write_json(pdir / "selection.json", selection)

    def load_selection(self, project_id: str) -> Optional[dict]:
        """Load scene selection."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "selection.json")

    # ─── Outputs ───────────────────────────────────────────

    def save_output(self, project_id: str, output: dict) -> None:
        """Register a rendered output."""
        pdir = self._ensure_project(project_id)
        outputs = self._read_json(pdir / "outputs.json", [])
        outputs.append(output)
        self._write_json(pdir / "outputs.json", outputs)

    def load_outputs(self, project_id: str) -> list[dict]:
        """Load all outputs for a project."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "outputs.json", [])

    # ─── QC ────────────────────────────────────────────────

    def save_qc_report(self, project_id: str, output_id: str, report: dict) -> None:
        """Save QC report for an output."""
        pdir = self._ensure_project(project_id)
        self._write_json(pdir / "qc" / f"{output_id}.json", report)

    def load_qc_report(self, project_id: str, output_id: str) -> Optional[dict]:
        """Load QC report for an output."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "qc" / f"{output_id}.json")

    # ─── Transcript ────────────────────────────────────────

    def save_transcript(self, project_id: str, transcript: dict) -> None:
        """Save full video transcript."""
        pdir = self._ensure_project(project_id)
        self._write_json(pdir / "transcript.json", transcript)

    def load_transcript(self, project_id: str) -> Optional[dict]:
        """Load transcript."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "transcript.json")

    # ─── Job Tracking ──────────────────────────────────────

    def save_job(self, project_id: str, job: dict) -> None:
        """Save/update a job record."""
        pdir = self._ensure_project(project_id)
        jobs = self._read_json(pdir / "jobs.json", [])
        # Update existing or append
        for i, j in enumerate(jobs):
            if j.get("id") == job.get("id"):
                jobs[i] = job
                break
        else:
            jobs.append(job)
        self._write_json(pdir / "jobs.json", jobs)

    def load_jobs(self, project_id: str) -> list[dict]:
        """Load all jobs for a project."""
        pdir = self._ensure_project(project_id)
        return self._read_json(pdir / "jobs.json", [])

    # ─── Thumbnails ────────────────────────────────────────

    def thumbnail_dir(self, project_id: str) -> Path:
        """Get the thumbnail directory for a project."""
        pdir = self._ensure_project(project_id)
        return pdir / "thumbnails"

    def output_dir(self, project_id: str) -> Path:
        """Get the output directory for a project."""
        pdir = self._ensure_project(project_id)
        return pdir / "outputs"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pantry — Video Kitchen metadata store")
    parser.add_argument("--base-dir", default="./projects")
    parser.add_argument("action", choices=["list", "info", "delete"])
    parser.add_argument("--project-id", help="Project ID for info/delete")

    args = parser.parse_args()
    pantry = Pantry(args.base_dir)

    if args.action == "list":
        projects = pantry.list_projects()
        for p in projects:
            status = p.get("status", "?")
            title = p.get("title", "?")
            pid = p.get("id", "?")
            print(f"  {pid}  [{status}]  {title}")
        if not projects:
            print("  (no projects)")

    elif args.action == "info":
        if not args.project_id:
            print("Error: --project-id required for info")
            sys.exit(1)
        meta = pantry.get_project(args.project_id)
        print(json.dumps(meta, indent=2))
        scenes = pantry.load_scenes(args.project_id)
        print(f"\nScenes: {len(scenes)}")

    elif args.action == "delete":
        if not args.project_id:
            print("Error: --project-id required for delete")
            sys.exit(1)
        pantry.delete_project(args.project_id)
        print(f"Deleted: {args.project_id}")
