#!/usr/bin/env python3
"""
timeline.py — Project Timeline Viewer for FFWD Kitchen

Generates an HTML timeline view showing video clips, VO, O-Ton, and music tracks
like a video editor (CapCut style).

Usage:
    python3 scripts/timeline.py --project rapid392
    python3 scripts/timeline.py --project rapid392 --serve 8080
"""
import json, os, sys, webbrowser
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = f"{BASE}/assets"


def get_track_color(track_type):
    colors = {
        "video": "#4CAF50",
        "vo": "#2196F3",
        "oton": "#FF9800",
        "music": "#9C27B0",
        "subtitle": "#F44336",
        "silence": "#555555",
    }
    return colors.get(track_type, "#666")


def load_project_timeline(project_id):
    """Load project data and reconstruct timeline from clips."""
    proj_dir = f"{BASE}/projects/{project_id}"
    if not os.path.isdir(proj_dir):
        return None

    # Load project metadata
    meta = {}
    meta_path = f"{proj_dir}/project.json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)

    # Load transcript
    transcript = []
    trans_path = f"{proj_dir}/transcript.json"
    if os.path.exists(trans_path):
        with open(trans_path) as f:
            d = json.load(f)
            transcript = d.get("segments", [])

    # Load w24 metadata
    w24_meta = {}
    w24_path = f"{proj_dir}/w24_meta.json"
    if os.path.exists(w24_path):
        with open(w24_path) as f:
            w24_meta = json.load(f)

    # Load receipt
    receipt = {}
    receipt_path = f"{proj_dir}/receipt.json"
    if os.path.exists(receipt_path):
        with open(receipt_path) as f:
            receipt = json.load(f)

    # Scan for output files to determine timeline
    clips = []
    concat_files = []

    # Look for concat.txt (most recent build)
    for cname in ["concat.txt", "v2_concat.txt", "v2_concat2.txt", "concat_v2.txt"]:
        cp = f"{proj_dir}/{cname}"
        if os.path.exists(cp):
            with open(cp) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("file '"):
                        fname = line[6:-1]
                        concat_files.append(fname)

    # Reconstruct tracks from concat file entries
    video_track = []
    audio_track = []
    oton_track = []
    music_track = []
    subtitle_track = []

    # Parse concat entries into timeline items
    time_offset = 0
    for fname in concat_files:
        fpath = f"{proj_dir}/{fname}"
        if not os.path.exists(fpath):
            continue
        dur_r = os.popen(f"ffprobe -v quiet -print_format json -show_format '{fpath}'").read()
        try:
            dur = float(json.loads(dur_r)["format"]["duration"])
        except:
            dur = 3.0

        name_lower = fname.lower()
        label = fname.replace("_s.mp4", "").replace(".mp4", "").replace("_", " ")

        if "ot" in name_lower or "oton" in name_lower:
            oton_track.append({
                "start": time_offset, "duration": dur, "label": label,
                "file": fname, "color": get_track_color("oton")
            })
            video_track.append({
                "start": time_offset, "duration": dur, "label": label,
                "file": fname, "color": get_track_color("video")
            })
        elif "vo" in name_lower and "surv" not in name_lower:
            audio_track.append({
                "start": time_offset, "duration": dur, "label": label,
                "file": fname, "color": get_track_color("vo")
            })
        else:
            video_track.append({
                "start": time_offset, "duration": dur, "label": label,
                "file": fname, "color": get_track_color("video")
            })

        time_offset += dur

    total_duration = time_offset

    # Add VO track (estimate from VO file)
    vo_path = None
    for vp in ["vo.mp3", "v2_vo.mp3"]:
        if os.path.exists(f"{proj_dir}/{vp}"):
            vo_path = f"{proj_dir}/{vp}"
            break

    if vo_path:
        dur_r = os.popen(f"ffprobe -v quiet -print_format json -show_format '{vo_path}'").read()
        try:
            vo_dur = float(json.loads(dur_r)["format"]["duration"])
            audio_track.append({
                "start": 2.0, "duration": vo_dur, "label": "VO (TTS onyx)",
                "file": os.path.basename(vo_path), "color": get_track_color("vo")
            })
        except:
            pass

    # Music track spans entire duration
    if total_duration > 0:
        music_track.append({
            "start": 0, "duration": total_duration, "label": "Shelter — To The Valley",
            "file": "shelter_to_the_valley.mp3", "color": get_track_color("music")
        })

    return {
        "project_id": project_id,
        "meta": meta,
        "w24": w24_meta,
        "receipt": receipt,
        "transcript": transcript,
        "total_duration": total_duration,
        "tracks": {
            "Video": video_track,
            "VO": audio_track,
            "O-Ton": oton_track,
            "Music": music_track,
        }
    }


def render_html(data):
    """Render timeline as interactive HTML page."""
    tracks = data["tracks"]
    total_dur = max(data["total_duration"], 1)
    px_per_sec = 30  # pixels per second

    total_width = int(total_dur * px_per_sec) + 200

    track_rows = ""
    for track_name, items in tracks.items():
        items_html = ""
        for item in items:
            left = int(item["start"] * px_per_sec)
            width = max(int(item["duration"] * px_per_sec), 8)
            color = item.get("color", "#666")
            label = item.get("label", "")
            items_html += f"""
            <div class="clip" style="left:{left}px;width:{width}px;background:{color};"
                 title="{label} ({item['duration']:.1f}s)">
                <span class="clip-label">{label[:25]}</span>
            </div>"""

        track_rows += f"""
        <div class="track">
            <div class="track-label">{track_name}</div>
            <div class="track-content" style="width:{total_width}px">
                {items_html}
            </div>
        </div>"""

    # Time ruler
    ruler_marks = ""
    for t in range(0, int(total_dur) + 1):
        left = int(t * px_per_sec)
        if t % 5 == 0:
            ruler_marks += f'<div class="ruler-mark major" style="left:{left}px"><span>{t}s</span></div>'
        elif t % 1 == 0:
            ruler_marks += f'<div class="ruler-mark" style="left:{left}px"></div>'

    # Transcript preview
    trans_html = ""
    for seg in data["transcript"][:30]:
        trans_html += f'<div class="trans-seg"><span class="trans-time">{seg["start"]:.0f}s</span> {seg["text"][:100]}</div>\n'

    meta = data["meta"]
    w24 = data["w24"]

    receipt_lines = ""
    if data["receipt"] and data["receipt"].get("items"):
        for item in data["receipt"]["items"]:
            receipt_lines += f'<div class="line"><span>{item[0]}</span><span>${item[2]:.3f}</span></div>'

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>🎬 VIDEO KITCHEN — {data['project_id']}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #1a1a2e; color: #eee; font-family: 'SF Mono', 'Fira Code', monospace; }}
    .header {{ background: #16213e; padding: 20px; border-bottom: 2px solid #4CAF50; }}
    .header h1 {{ font-size: 18px; color: #4CAF50; }}
    .header h2 {{ font-size: 14px; color: #888; margin-top: 4px; }}
    .header .meta {{ display: flex; gap: 20px; margin-top: 10px; font-size: 12px; color: #aaa; }}

    .tabs {{ display: flex; background: #0f3460; padding: 0; }}
    .tab {{ padding: 10px 20px; cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; color: #888; }}
    .tab.active {{ color: #4CAF50; border-bottom-color: #4CAF50; background: #1a1a2e; }}

    .tab-content {{ display: none; padding: 20px; }}
    .tab-content.active {{ display: block; }}

    .timeline {{ overflow-x: auto; padding: 10px 0; }}
    .ruler {{ position: relative; height: 25px; margin-left: 120px; border-bottom: 1px solid #333; }}
    .ruler-mark {{ position: absolute; top: 0; height: 100%; border-left: 1px solid #444; }}
    .ruler-mark.major {{ border-left-color: #666; }}
    .ruler-mark span {{ position: absolute; top: 2px; left: 4px; font-size: 10px; color: #888; }}

    .track {{ display: flex; height: 50px; margin: 2px 0; }}
    .track-label {{ width: 120px; min-width: 120px; display: flex; align-items: center;
                   justify-content: flex-end; padding-right: 10px; font-size: 12px;
                   color: #888; text-transform: uppercase; }}
    .track-content {{ position: relative; height: 100%; background: #0f0f23; border-radius: 4px; }}

    .clip {{ position: absolute; top: 4px; height: 42px; border-radius: 4px; opacity: 0.85;
             cursor: pointer; display: flex; align-items: center; padding: 0 6px;
             transition: opacity 0.2s; overflow: hidden; }}
    .clip:hover {{ opacity: 1; }}
    .clip-label {{ font-size: 9px; white-space: nowrap; color: #fff; text-shadow: 0 1px 2px #000; }}

    .transcript {{ max-height: 400px; overflow-y: auto; }}
    .trans-seg {{ padding: 4px 10px; font-size: 12px; border-bottom: 1px solid #222; }}
    .trans-seg:hover {{ background: #222; }}
    .trans-time {{ color: #4CAF50; margin-right: 8px; font-weight: bold; }}

    .receipt {{ background: #0f0f23; border: 1px solid #333; border-radius: 8px; padding: 20px;
               max-width: 400px; font-size: 13px; line-height: 1.8; }}
    .receipt h3 {{ color: #4CAF50; text-align: center; margin-bottom: 10px; }}
    .receipt .line {{ display: flex; justify-content: space-between; }}
    .receipt .total {{ border-top: 1px solid #333; padding-top: 8px; font-weight: bold; color: #4CAF50; }}

    .legend {{ display: flex; gap: 15px; margin: 10px 0 15px 120px; font-size: 11px; }}
    .legend-item {{ display: flex; align-items: center; gap: 5px; }}
    .legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}
</style>
</head>
<body>

<div class="header">
    <h1>▶️▶️▶️ VIDEO KITCHEN — Timeline</h1>
    <h2>{meta.get('title', data['project_id'])}</h2>
    <div class="meta">
        <span>📅 {w24.get('sendungVom', meta.get('updated_at', '?')[:10])}</span>
        <span>🎬 {data['total_duration']:.1f}s</span>
        <span>📝 {len(data['transcript'])} Segments</span>
        <span>💰 ${data['receipt'].get('total', 0):.3f}</span>
        <span>🔑 {w24.get('idProduction', '?')}</span>
    </div>
</div>

<div class="tabs">
    <div class="tab active" onclick="showTab('timeline')">🎬 Timeline</div>
    <div class="tab" onclick="showTab('transcript')">📝 Transcript</div>
    <div class="tab" onclick="showTab('receipt')">🧾 Receipt</div>
    <div class="tab" onclick="showTab('info')">ℹ️ Info</div>
</div>

<div id="tab-timeline" class="tab-content active">
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:#4CAF50"></div> Video</div>
        <div class="legend-item"><div class="legend-dot" style="background:#2196F3"></div> VO</div>
        <div class="legend-item"><div class="legend-dot" style="background:#FF9800"></div> O-Ton</div>
        <div class="legend-item"><div class="legend-dot" style="background:#9C27B0"></div> Music</div>
    </div>
    <div class="timeline">
        <div class="ruler" style="width:{total_width}px">
            {ruler_marks}
        </div>
        {track_rows}
    </div>
</div>

<div id="tab-transcript" class="tab-content">
    <h3 style="margin-bottom:10px;color:#4CAF50;">📝 Transcript ({len(data['transcript'])} segments)</h3>
    <div class="transcript">
        {trans_html}
    </div>
</div>

<div id="tab-receipt" class="tab-content">
    <div class="receipt">
        <h3>🧾 VIDEO KITCHEN<br>Finest Teaser Soul Food</h3>
        <p style="text-align:center;color:#888;font-size:11px;">{data['project_id']} · {datetime.now().strftime('%Y-%m-%d')}</p>
        <br>
        {receipt_lines if receipt_lines else '<p>No receipt</p>'}
        <div class="total line">
            <span>TOTAL</span>
            <span>${data["receipt"].get("total", 0):.3f}</span>
        </div>
    </div>
</div>

<div id="tab-info" class="tab-content">
    <h3 style="margin-bottom:10px;color:#4CAF50;">ℹ️ Project Info</h3>
    <pre style="background:#0f0f23;padding:15px;border-radius:8px;font-size:12px;line-height:1.6;overflow:auto;">{json.dumps({**meta, **w24}, indent=2, ensure_ascii=False)}</pre>
</div>

<script>
function showTab(id) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + id).classList.add('active');
    event.target.classList.add('active');
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Kitchen Timeline Viewer")
    p.add_argument("--project", required=True, help="Project ID")
    p.add_argument("--serve", type=int, help="Serve on port (optional)")
    p.add_argument("--output", help="Output HTML file path")
    args = p.parse_args()

    data = load_project_timeline(args.project)
    if not data:
        print(f"Project '{args.project}' not found.")
        sys.exit(1)

    html = render_html(data)

    out_path = args.output or f"{BASE}/projects/{args.project}/timeline.html"
    with open(out_path, "w") as f:
        f.write(html)

    print(f"✅ Timeline generated: {out_path}")
    print(f"   Duration: {data['total_duration']:.1f}s | Tracks: {len(data['tracks'])} | Segments: {len(data['transcript'])}")

    if args.serve:
        import http.server
        import threading

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=os.path.dirname(out_path), **kw)

        server = http.server.HTTPServer(("0.0.0.0", args.serve), Handler)
        print(f"🌐 Serving at http://localhost:{args.serve}/{os.path.basename(out_path)}")
        threading.Timer(1, lambda: webbrowser.open(f"http://localhost:{args.serve}/{os.path.basename(out_path)}")).start()
        server.serve_forever()
