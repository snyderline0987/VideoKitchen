#!/usr/bin/env python3
"""
cost_calc.py — Kitchen Bill / Cost Calculator for FFWD Trailer Kitchen
Usage:
    python3 scripts/cost_calc.py --project feicht --audio-min 25 --tts-hd-chars 200
"""

import json, os, sys
from datetime import datetime, timezone

RATES = {
    "whisper":        0.006,      # per minute
    "tts_hd":         0.030,      # per 1K chars
    "tts_standard":   0.015,      # per 1K chars
    "elevenlabs":     0.300,      # per 1K chars
    "vision":         0.005,      # per call
    "gpt4o_mini":     0.00015,    # per 1K tokens
    "agent_in":       0.0000015,  # per token (varies by model)
    "agent_out":      0.000006,   # per token (varies by model)
}

def calc(project, audio_min=0, tts_hd_chars=0, tts_chars=0,
         elevenlabs_chars=0, vision_calls=0, gpt4o_mini_tokens=0,
         agent_in_tokens=0, agent_out_tokens=0, notes=""):
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
    if agent_in_tokens > 0 or agent_out_tokens > 0:
        c = (agent_in_tokens * RATES["agent_in"]) + (agent_out_tokens * RATES["agent_out"])
        total_tok = agent_in_tokens + agent_out_tokens
        items.append(("Küchenchef (Agent LLM)", f"{total_tok:,} Tokens", c))

    total = sum(it[2] for it in items)
    tip_suggestion = round(total * 0.15, 4)

    return {
        "project": project,
        "ts": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "total": round(total, 4),
        "tip": tip_suggestion,
        "notes": notes,
    }

def bill(receipt):
    lines = []
    lines.append("  ╔══════════════════════════════════╗")
    lines.append("  ║  ▶️▶️▶️ VIDEO KITCHEN              ║")
    lines.append("  ║  Finest Teaser Soul Food          ║")
    lines.append("  ║  & Geschmackige Video Roasts      ║")
    lines.append("  ╚══════════════════════════════════╝")
    lines.append("")
    lines.append(f"  Projekt:   {receipt['project']}")
    p = receipt['project'].upper().replace('-','.')
    lines.append(f"  Token:     #{p}.{receipt['ts'][:10].replace('-','')}")
    lines.append(f"  Datum:     {receipt['ts'][:16].replace('T',' ')}")
    lines.append("  ─────────────────────────────────────")
    lines.append("")
    for label, qty, cost in receipt['items']:
        lines.append(f"  {label}")
        lines.append(f"    {qty}              ${cost:.4f}")
        lines.append("")
    lines.append("  ─────────────────────────────────────")
    lines.append(f"  ZWISCHENSUMME              ${receipt['total']:.4f}")
    lines.append("")
    lines.append(f"  💰 Trinkgeld (15%)          ${receipt['tip']:.4f}")
    lines.append(f"  ─────────────────────────────────────")
    lines.append(f"  GESAMT                     ${receipt['total'] + receipt['tip']:.4f}")
    lines.append("  ─────────────────────────────────────")
    lines.append("")
    lines.append("  Zahlungsart:   API-Guthoben")
    lines.append("  Serviert von:  Küchenchef Agent")
    lines.append("  Danke für Ihren Besuch! 🍽️")
    lines.append("")
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
    p.add_argument("--agent-in-tokens", type=int, default=0)
    p.add_argument("--agent-out-tokens", type=int, default=0)
    p.add_argument("--notes", default="")
    p.add_argument("--ledger", default="cost_ledger.json")
    p.add_argument("--no-log", action="store_true")
    a = p.parse_args()
    r = calc(a.project, a.audio_min, a.tts_hd_chars, a.tts_chars,
             a.elevenlabs_chars, a.vision_calls, a.gpt_tokens,
             a.agent_in_tokens, a.agent_out_tokens, a.notes)
    print(bill(r))
    if not a.no_log:
        lp = save(r, a.ledger)
        print(f"  Quittung archiviert: {lp}")
    pd = f"projects/{a.project}"
    if os.path.isdir(pd):
        with open(f"{pd}/receipt.json", "w") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
