#!/usr/bin/env python3
"""
dashboard.py — VIDEO KITCHEN Dashboard
Shows all projects, costs, pipeline status.
Usage: python3 scripts/dashboard.py
"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = f"{BASE}/projects"
LEDGER_PATH = f"{BASE}/cost_ledger.json"

def load_projects():
    projects = []
    if not os.path.isdir(PROJECTS_DIR):
        return projects
    for d in sorted(os.listdir(PROJECTS_DIR)):
        ppath = f"{PROJECTS_DIR}/{d}"
        if not os.path.isdir(ppath):
            continue
        pj = f"{ppath}/project.json"
        meta = {}
        if os.path.exists(pj):
            with open(pj) as f:
                meta = json.load(f)
        outputs = [f for f in os.listdir(ppath)
                    if f.endswith('.mp4') and ('final' in f or f.startswith('feicht_v') or f.startswith('v2') or f.startswith('v3') or f.startswith('v4'))]
        receipt_path = f"{ppath}/receipt.json"
        cost = None
        if os.path.exists(receipt_path):
            with open(receipt_path) as f:
                cost = json.load(f).get("total")
        projects.append({
            "id": d,
            "title": meta.get("title", d),
            "status": meta.get("status", "?"),
            "updated": str(meta.get("updated_at", "?"))[:16],
            "outputs": outputs,
            "cost": cost,
        })
    return projects

def load_ledger():
    if not os.path.exists(LEDGER_PATH):
        return [], 0
    with open(LEDGER_PATH) as f:
        ledger = json.load(f)
    return ledger, sum(r["total"] for r in ledger)

def render(projects=None, ledger=None, total_cost=0):
    if projects is None:
        projects = load_projects()
    if ledger is None:
        ledger, total_cost = load_ledger()

    lines = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════╗")
    lines.append("║  ▶️▶️▶️  VIDEO KITCHEN — Dashboard                     ║")
    lines.append("║  Finest Teaser Soul Food & Geschmackige Roasts      ║")
    lines.append("╚══════════════════════════════════════════════════════╝")
    lines.append("")
    lines.append(f"  📂 Projekte:      {len(projects)}")
    lines.append(f"  🎬 Teaser ready:  {sum(1 for p in projects if p['outputs'])}")
    lines.append(f"  🧾 Kosten total:  ${total_cost:.4f} ({len(ledger)} Rechnungen)")
    lines.append("")
    lines.append("  ─────────────────────────────────────────────────────")
    lines.append(f"  {'PROJEKT':33s} {'STATUS':11s} {'OUTPUT':8s} KOSTEN")
    lines.append("  ─────────────────────────────────────────────────────")

    for p in projects:
        title = p["title"][:32]
        status = p["status"][:10]
        cost_str = f"${p['cost']:.3f}" if p["cost"] else "-"
        out_count = len(p["outputs"])
        out_str = f"{out_count}x MP4" if out_count else "-"
        lines.append(f"  {title:33s} {status:11s} {out_str:8s} {cost_str}")

    lines.append("  ─────────────────────────────────────────────────────")
    lines.append("")
    lines.append("  🔧 Pipeline: prep → score → story → plate → season")
    lines.append(f"  💰 Küchenkonto: ${total_cost:.4f}")
    lines.append(f"  📅 Letztes Update: {projects[-1]['updated'] if projects else '?'}")
    lines.append("")
    return "\n".join(lines)

if __name__ == "__main__":
    print(render())
