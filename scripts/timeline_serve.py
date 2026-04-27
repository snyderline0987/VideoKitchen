#!/usr/bin/env python3
"""
timeline_serve.py — Timeline viewer server.
Serves Remotion React app + project data JSON endpoints.

Usage:
    python3 scripts/timeline_serve.py --project rapid392
    python3 scripts/timeline_serve.py --project rapid392 --port 5173
"""
import json, os, subprocess, http.server, json, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE, "timeline-app")
PROJECTS_DIR = os.path.join(BASE, "projects")

def load_project_timeline(project_id):
    proj_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.isdir(proj_dir):
        return None

    meta = json.load(open(os.path.join(proj_dir, "project.json")))\
        if os.path.exists(os.path.join(proj_dir, "project.json")) else {}

    transcript = json.load(open(os.path.join(proj_dir, "transcript.json")))\
        .get("segments", []) if os.path.exists(os.path.join(proj_dir, "transcript.json")) else []

    w24 = json.load(open(os.path.join(proj_dir, "w24_meta.json")))\
        if os.path.exists(os.path.join(proj_dir, "w24_meta.json")) else {}

    receipt = {}
    ledger_path = os.path.join(BASE, "cost_ledger.json")
    if os.path.exists(ledger_path):
        ledger = json.load(open(ledger_path))
        if isinstance(ledger, list):
            for e in ledger:
                if project_id in e.get("project", "").replace(" ", "").lower():
                    receipt = e; break
        elif isinstance(ledger, dict):
            for e in ledger.get("entries", []):
                if project_id in e.get("project", "").replace(" ", "").lower():
                    receipt = e; break

    video_track = []
    oton_track = []
    audio_track = []
    music_track = []
    total_dur = meta.get("duration", 30)

    for cname in ["concat.txt", "v2_concat.txt", "v2_concat2.txt"]:
        cp = os.path.join(proj_dir, cname)
        if not os.path.exists(cp): continue
        offset = 0
        for line in open(cp):
            line = line.strip()
            if not line.startswith("file '"): continue
            fname = line[6:-1]
            fpath = os.path.join(proj_dir, fname)
            if not os.path.exists(fpath): continue
            r = subprocess.run(f"ffprobe -v quiet -print_format json -show_format '{fpath}'",
                               shell=True, capture_output=True, text=True)
            dur = 3.0
            try: dur = float(json.loads(r.stdout)["format"]["duration"])
            except: pass
            hl = fname.replace("_s.mp4","").replace("_sub.mp4","").replace(".mp4","").replace("_"," ")
            entry = {"start": offset, "duration": dur, "label": hl, "file": fname}
            video_track.append({**entry, "color": "#4CAF50"})
            if "ot" in fname.lower():
                oton_track.append({**entry, "color": "#FF9800"})
            offset += dur
        total_dur = max(total_dur, offset)
        break

    # VO file
    for v in ["vo.mp3", "v2_vo.mp3"]:
        vp = os.path.join(proj_dir, v)
        if os.path.exists(vp):
            r = subprocess.run(f"ffprobe -v quiet -print_format json -show_format '{vp}'",
                               shell=True, capture_output=True, text=True)
            try:
                vd = float(json.loads(r.stdout)["format"]["duration"])
                audio_track.append({"start": 2.0, "duration": vd, "label": "VO (onyx)", "file": v, "color": "#2196F3"})
            except: pass
            break

    if total_dur > 0:
        music_track.append({"start": 0, "duration": total_dur, "label": "Shelter", "file": "shelter_to_the_valley.mp3", "color": "#9C27B0"})

    return {
        "project_id": project_id, "meta": meta, "w24": w24,
        "receipt": receipt, "transcript": transcript,
        "total_duration": total_dur,
        "tracks": {"Video": video_track, "VO": audio_track, "O-Ton": oton_track, "Music": music_track},
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        pid = getattr(self.server, "_pid", "rapid392")
        if self.path == "/project.json":
            meta_path = os.path.join(PROJECTS_DIR, pid, "project.json")
            if os.path.exists(meta_path):
                self._json(json.load(open(meta_path)))
            else:
                self._json({"id": pid, "title": pid})
            return
        if self.path == "/timeline_data.json":
            data = load_project_timeline(pid)
            if data: self._json(data)
            else: self.send_error(404, f"Project {pid} not found")
            return
        super().do_GET()

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, fmt, *a):
        if a[1] != 304:  # skip 304s
            super().log_message(fmt, *a)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--port", type=int, default=5173)
    args = p.parse_args()

    proj_dir = os.path.join(PROJECTS_DIR, args.project)
    if not os.path.isdir(proj_dir):
        print(f"❌ Project '{args.project}' not found")
        sys.exit(1)

    server = http.server.HTTPServer(("0.0.0.0", args.port), Handler)
    server._pid = args.project

    print(f"🎬 Kitchen Timeline — {args.project}")
    print(f"   http://localhost:{args.port}")

    rebuild = os.path.join(DIST_DIR, "dist")
    if os.path.isdir(rebuild):
        os.chdir(rebuild)
    else:
        print("   (no dist/ — will serve src/)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋")