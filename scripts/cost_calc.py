#!/usr/bin/env python3
"""
cost_calc.py — Kitchen Bill / Cost Calculator for FFWD Trailer Kitchen
Usage:
    python3 scripts/cost_calc.py --project feicht --audio-min 25 --tts-chars 200
"""

import json, os, sys
from datetime import datetime, timezone

RATES = {
    "whisper":        0.006,
    "tts_hd":         0.030,
    "tts_standard":   0.015,
    "elevenlabs":     0.300,
    "vision":         0.005,
    "gpt4o_mini":     0.00015,
    "agent_tokens":   0.00000015,
}

def calc(project, audio_min=0, tts_hd_chars=0, tts_chars=0,
         elevenlabs_chars=0, vision_calls=0, gpt4o_mini_tokens=0,
         agent_tokens=0, notes=""):
    items = []
    if audio_min > 0:
        c = audio_min * RATES["whisper"]
        items.append(("Transkription (Whisper API)", f"{audio_min:.0f} Min", c))
    if tts_hd_chars > 0:
        c = tts_hd_chars / 1000 * RATES["tts_hd"]
        items.append(("Sprachausgabe (OpenAI TTS HD)", f"{tts_hd_chars} Zeichen", c))
    elif tts_chars > 0:
        c = tts_chars / 1000 * RATES["tts_standard"]
        items.append(("Sprachausgabe (OpenAI TTS)", f"{tts_chars} Zeichen", c))
    if elevenlabs_chars > 0:
        c = elevenlabs_chars / 1000 * RATES["elevenlabs"]
        items.append(("ElevenLabs TTS", f"{elevenlabs_chars} Zeichen", c))
    if vision_calls > 0:
        c = vision_calls * RATES["vision"]
        items.append(("Bildanalyse (Vision)", f"{vision_calls} Calls", c))
    if gpt4o_mini_tokens > 0:
        c = gpt4o_mini_tokens / 1000 * RATES["gpt4o_mini"]
        items.append(("GPT-4o-mini Scoring", f"{gpt4o_mini_tokens} Tokens", c))
    total = sum(it[2] for it in items)
    return {"project": project, "ts": datetime.now(timezone.utc).isoformat(),
            "items": items, "total": round(total, 4), "notes": notes}

def bill(receipt):
    lines = []
    lines.append("  ╔══════════════════════════╗")
    lines.append("  ║     K Ü C H E N -       ║")
    lines.append("  ║       R E C H N U N G   ║")
    lines.append("  ╚══════════════════════════╝")
    p = receipt['project'].upper().replace('-','.')
    lines.append(f"\n  Projekt:   {receipt['project']}")
    lines.append(f"  Token:     #{p}.{receipt['ts'][:10].replace('-','')}")
    lines.append("  ─────────────────────────────")
    for label, qty, cost in receipt['items']:
        lines.append(f"\n  {label:30s}")
        lines.append(f"  {qty:25s}      ${cost:.3f}")
    lines.append("\n  ─────────────────────────────")
    lines.append(f"  GESAMT                      ${receipt['total']:.4f}")
    lines.append("  ─────────────────────────────")
    lines.append("\n  Serviert von: FFWD Kitchen Agent\n")
    return "\n".join(lines)

def save(receipt, ledger_path="cost_ledger.json"):
    ledger = []
    if os.path.exists(ledger_path):
        with open(ledger_path) as f:
            ledger = json.load(f)
    ledger.append(receipt)
    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)
    return ledger_path

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--project", default="unknown")
    p.add_argument("--audio-min", type=float, default=0)
    p.add_argument("--tts-hd-chars", type=int, default=0)
    p.add_argument("--tts-chars", type=int, default=0)
    p.add_argument("--elevenlabs-chars", type=int, default=0)
    p.add_argument("--vision-calls", type=int, default=0)
    p.add_argument("--gpt-tokens", type=int, default=0)
    p.add_argument("--agent-tokens", type=int, default=0)
    p.add_argument("--notes", default="")
    p.add_argument("--ledger", default="cost_ledger.json")
    p.add_argument("--no-log", action="store_true")
    a = p.parse_args()
    r = calc(a.project, a.audio_min, a.tts_hd_chars, a.tts_chars,
             a.elevenlabs_chars, a.vision_calls, a.gpt_tokens,
             a.agent_tokens, a.notes)
    print(bill(r))
    if not a.no_log:
        lp = save(r, a.ledger)
        print(f"  Quittung archiviert: {lp}")
    pd = f"projects/{a.project}"
    if os.path.isdir(pd):
        with open(f"{pd}/receipt.json", "w") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)