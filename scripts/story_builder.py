#!/usr/bin/env python3
"""
story_builder.py — Narrative Arc Engine for Video Kitchen v0.9.0

Builds story arcs from analyzed scenes. Not just rating — storytelling.

Given scored scenes (visual, audio, transcript, combined scores), this engine:
  1. Identifies narrative beats (hook, rising action, climax, resolution)
  2. Builds a storyboard with optimal scene ordering
  3. Generates VO suggestions for each beat
  4. Computes pacing and emotional rhythm
  5. Suggests music mood transitions

Usage:
    from story_builder import StoryBuilder
    builder = StoryBuilder(project_dir="./projects/my_proj")
    storyboard = builder.build(scenes, recipe="social_teaser_w24", target_duration=25)

    # CLI
    python3 story_builder.py --project-dir ./projects/my_proj --recipe social_teaser_w24
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

import numpy as np


# ─── Narrative Beat Types ───────────────────────────────────────────

BEAT_TYPES = {
    "hook": {
        "name": "Hook",
        "description": "Grab attention in first 2-3 seconds",
        "ideal_duration": (1.5, 4.0),
        "ideal_score": (0.6, 1.0),  # High visual/audio impact
        "vo_style": "punchy_question",
    },
    "setup": {
        "name": "Setup",
        "description": "Introduce context, characters, stakes",
        "ideal_duration": (2.0, 6.0),
        "ideal_score": (0.3, 0.7),
        "vo_style": "contextual",
    },
    "rising_action": {
        "name": "Rising Action",
        "description": "Build tension, introduce conflict",
        "ideal_duration": (2.0, 8.0),
        "ideal_score": (0.4, 0.8),
        "vo_style": "building",
    },
    "climax": {
        "name": "Climax",
        "description": "Peak emotional moment, biggest reveal",
        "ideal_duration": (2.0, 6.0),
        "ideal_score": (0.7, 1.0),
        "vo_style": "revelation",
    },
    "twist": {
        "name": "Twist",
        "description": "Unexpected turn, subvert expectations",
        "ideal_duration": (1.5, 4.0),
        "ideal_score": (0.6, 1.0),
        "vo_style": "surprise",
    },
    "resolution": {
        "name": "Resolution",
        "description": "Payoff, CTA, or emotional landing",
        "ideal_duration": (1.5, 5.0),
        "ideal_score": (0.4, 0.8),
        "vo_style": "cta",
    },
    "outro": {
        "name": "Outro",
        "description": "Logo, branding, social handle",
        "ideal_duration": (1.0, 3.0),
        "ideal_score": (0.1, 0.5),
        "vo_style": "branding",
    },
}

# ─── Story Templates by Recipe ──────────────────────────────────────

STORY_TEMPLATES = {
    "social_teaser_w24": {
        "beats": ["hook", "setup", "rising_action", "climax", "resolution", "outro"],
        "target_duration": (20, 30),
        "scene_count": (4, 6),
        "pacing": "fast",  # quick cuts, high energy
        "music_arc": "build_drop",
    },
    "spicy_trailer": {
        "beats": ["hook", "setup", "rising_action", "climax", "twist", "resolution"],
        "target_duration": (30, 45),
        "scene_count": (5, 8),
        "pacing": "dynamic",  # varied rhythm
        "music_arc": "epic_build",
    },
    "highlight_abendsendung": {
        "beats": ["hook", "setup", "rising_action", "climax", "resolution"],
        "target_duration": (60, 90),
        "scene_count": (6, 12),
        "pacing": "professional",  # steady, informative
        "music_arc": "steady_build",
    },
    "bts_soup": {
        "beats": ["hook", "setup", "rising_action", "climax", "resolution", "outro"],
        "target_duration": (45, 60),
        "scene_count": (5, 8),
        "pacing": "chill",  # relaxed, organic
        "music_arc": "lofi_build",
    },
}


@dataclass
class StoryBeat:
    """A single beat in the story arc."""
    beat_type: str
    scene_index: int
    start_time: float
    end_time: float
    duration: float
    score: float
    visual_score: float
    audio_score: float
    transcript_score: float
    transcript: str
    thumbnail: Optional[str] = None
    vo_suggestion: Optional[str] = None
    music_intensity: float = 0.5  # 0-1, maps to music volume/energy
    transition: str = "cut"  # cut, crossfade, fade, etc.


@dataclass
class Storyboard:
    """Complete storyboard for a teaser/trailer."""
    recipe: str
    target_duration: float
    actual_duration: float
    beats: list[StoryBeat]
    scenes_used: list[int]
    scenes_skipped: list[int]
    narrative_arc: list[str]  # Beat type sequence
    pacing_profile: list[float]  # Intensity over time (0-1)
    music_mood: str
    music_bpm: str
    vo_style: str
    aspect_ratio: str
    story_summary: str
    title_suggestion: Optional[str] = None
    hashtag_suggestions: Optional[list] = None


class StoryBuilder:
    """Build narrative arcs from scored scenes."""

    def __init__(self, project_dir: str, llm_enabled: bool = True):
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.llm_enabled = llm_enabled

    # ─── Public API ────────────────────────────────────────

    def build(
        self,
        scenes: list[dict],
        recipe: str = "social_teaser_w24",
        target_duration: Optional[float] = None,
        min_score: float = 0.15,
    ) -> Storyboard:
        """
        Build a complete storyboard from scored scenes.

        Args:
            scenes: List of scored scene dicts from scoring.py
            recipe: Recipe name defining the story template
            target_duration: Override target duration (seconds)
            min_score: Minimum combined score for scene inclusion

        Returns:
            Storyboard with beats, pacing, and suggestions
        """
        template = self._get_template(recipe)
        target_dur = target_duration or self._pick_target_duration(template["target_duration"])
        beat_types = template["beats"]
        min_count, max_count = template["scene_count"]
        pacing = template["pacing"]

        # Filter scenes by minimum score
        candidates = [s for s in scenes if s.get("combined_score", 0) >= min_score]
        if not candidates:
            candidates = scenes  # Fallback: use all scenes

        # Sort by combined score descending for assignment
        scored = sorted(candidates, key=lambda s: s.get("combined_score", 0), reverse=True)

        # Assign scenes to beats
        beats = self._assign_beats(scored, beat_types, target_dur, min_count, max_count)

        # Reorder beats to story order (hook → setup → rising → climax → resolution → outro)
        story_order = {bt: i for i, bt in enumerate(beat_types)}
        beats.sort(key=lambda b: story_order.get(b.beat_type, 99))

        # Generate pacing profile (now in story order)
        pacing_profile = self._compute_pacing(beats, pacing)

        # Generate VO suggestions
        self._generate_vo_suggestions(beats)

        # Compute music intensity per beat
        self._compute_music_intensity(beats, pacing)

        # Build story summary
        story_summary = self._build_summary(beats)

        # Generate title and hashtags
        title, hashtags = self._generate_metadata(beats, recipe)

        return Storyboard(
            recipe=recipe,
            target_duration=target_dur,
            actual_duration=sum(b.duration for b in beats),
            beats=beats,
            scenes_used=[b.scene_index for b in beats],
            scenes_skipped=[s["scene_index"] for s in scenes if s["scene_index"] not in [b.scene_index for b in beats]],
            narrative_arc=[b.beat_type for b in beats],
            pacing_profile=pacing_profile,
            music_mood=template.get("music_mood", "upbeat"),
            music_bpm=template.get("music_bpm", "120-140"),
            vo_style=template.get("vo_style", "punchy"),
            aspect_ratio=template.get("aspect_ratio", "9:16"),
            story_summary=story_summary,
            title_suggestion=title,
            hashtag_suggestions=hashtags,
        )

    def save(self, storyboard: Storyboard, filename: str = "storyboard.json") -> Path:
        """Save storyboard to project directory."""
        output_path = self.project_dir / filename

        # Convert dataclass to dict
        data = {
            "recipe": storyboard.recipe,
            "target_duration": storyboard.target_duration,
            "actual_duration": storyboard.actual_duration,
            "beats": [asdict(b) for b in storyboard.beats],
            "scenes_used": storyboard.scenes_used,
            "scenes_skipped": storyboard.scenes_skipped,
            "narrative_arc": storyboard.narrative_arc,
            "pacing_profile": storyboard.pacing_profile,
            "music_mood": storyboard.music_mood,
            "music_bpm": storyboard.music_bpm,
            "vo_style": storyboard.vo_style,
            "aspect_ratio": storyboard.aspect_ratio,
            "story_summary": storyboard.story_summary,
            "title_suggestion": storyboard.title_suggestion,
            "hashtag_suggestions": storyboard.hashtag_suggestions,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[STORY] Storyboard saved to {output_path}")
        return output_path

    # ─── Beat Assignment ───────────────────────────────────

    def _assign_beats(
        self,
        scored_scenes: list[dict],
        beat_types: list[str],
        target_duration: float,
        min_count: int,
        max_count: int,
    ) -> list[StoryBeat]:
        """
        Assign scored scenes to narrative beats.

        Strategy:
          1. For each beat type, find the best matching scene
          2. Prefer scenes that match the beat's ideal score range
          3. Respect duration constraints
          4. Ensure temporal flow (beats roughly in chronological order)
        """
        beats = []
        used_indices = set()
        remaining_duration = target_duration

        for beat_type in beat_types:
            beat_spec = BEAT_TYPES[beat_type]
            ideal_dur_min, ideal_dur_max = beat_spec["ideal_duration"]
            ideal_score_min, ideal_score_max = beat_spec["ideal_score"]

            # Find best matching unused scene
            best_scene = None
            best_match_score = -1

            for scene in scored_scenes:
                idx = scene["scene_index"]
                if idx in used_indices:
                    continue

                dur = scene.get("duration", 0)
                score = scene.get("combined_score", 0)

                # Skip if too long for remaining duration
                if dur > remaining_duration and remaining_duration > 5:
                    continue

                # Compute match score: how well this scene fits this beat
                # Higher = better fit
                dur_match = 1.0 - abs(dur - (ideal_dur_min + ideal_dur_max) / 2) / max(ideal_dur_max, 5)
                score_match = 1.0 - abs(score - (ideal_score_min + ideal_score_max) / 2)

                # For hook/climax, strongly prefer high scores
                if beat_type in ("hook", "climax", "twist"):
                    score_match = score  # Directly use score

                # For setup/resolution, prefer mid scores
                if beat_type in ("setup", "resolution", "outro"):
                    score_match = 1.0 - abs(score - 0.5)

                match_score = 0.4 * dur_match + 0.6 * score_match

                # Bonus for scenes with transcripts (more content)
                if scene.get("transcript", "").strip():
                    match_score += 0.05

                if match_score > best_match_score:
                    best_match_score = match_score
                    best_scene = scene

            if best_scene:
                idx = best_scene["scene_index"]
                used_indices.add(idx)
                remaining_duration -= best_scene.get("duration", 0)

                beats.append(StoryBeat(
                    beat_type=beat_type,
                    scene_index=idx,
                    start_time=best_scene.get("start_time", 0),
                    end_time=best_scene.get("end_time", 0),
                    duration=best_scene.get("duration", 0),
                    score=best_scene.get("combined_score", 0),
                    visual_score=best_scene.get("visual_score", 0),
                    audio_score=best_scene.get("audio_score", 0),
                    transcript_score=best_scene.get("transcript_score", 0),
                    transcript=best_scene.get("transcript", ""),
                    thumbnail=best_scene.get("thumbnail", None),
                ))

        # If we have too few beats, add more from remaining scenes
        if len(beats) < min_count and len(used_indices) < len(scored_scenes):
            for scene in scored_scenes:
                idx = scene["scene_index"]
                if idx in used_indices:
                    continue
                if len(beats) >= max_count:
                    break

                # Assign as rising_action or setup
                beat_type = "rising_action" if len(beats) < max_count - 1 else "resolution"

                used_indices.add(idx)
                beats.append(StoryBeat(
                    beat_type=beat_type,
                    scene_index=idx,
                    start_time=scene.get("start_time", 0),
                    end_time=scene.get("end_time", 0),
                    duration=scene.get("duration", 0),
                    score=scene.get("combined_score", 0),
                    visual_score=scene.get("visual_score", 0),
                    audio_score=scene.get("audio_score", 0),
                    transcript_score=scene.get("transcript_score", 0),
                    transcript=scene.get("transcript", ""),
                    thumbnail=scene.get("thumbnail", None),
                ))

        return beats

    # ─── Pacing & Music ────────────────────────────────────

    def _compute_pacing(self, beats: list[StoryBeat], pacing_style: str) -> list[float]:
        """Compute intensity profile over the story duration."""
        if not beats:
            return []

        total_dur = sum(b.duration for b in beats)
        if total_dur <= 0:
            return []

        # Sample at 1-second intervals
        num_samples = max(10, int(total_dur))
        profile = []

        for i in range(num_samples):
            t = i * (total_dur / num_samples)

            # Find which beat we're in
            elapsed = 0
            current_beat = None
            for beat in beats:
                if elapsed <= t < elapsed + beat.duration:
                    current_beat = beat
                    break
                elapsed += beat.duration

            if not current_beat:
                profile.append(0.3)
                continue

            # Base intensity from beat type
            base_intensity = {
                "hook": 0.9,
                "setup": 0.4,
                "rising_action": 0.6,
                "climax": 1.0,
                "twist": 0.85,
                "resolution": 0.5,
                "outro": 0.3,
            }.get(current_beat.beat_type, 0.5)

            # Modulate by scene score
            score_factor = current_beat.score

            # Modulate by position in beat (entrance peak, sustain, exit)
            beat_progress = (t - elapsed) / max(current_beat.duration, 0.1)
            if beat_progress < 0.2:
                entrance_boost = 1.2  # Entrance bump
            elif beat_progress > 0.8:
                entrance_boost = 0.9  # Exit fade
            else:
                entrance_boost = 1.0

            intensity = base_intensity * (0.5 + 0.5 * score_factor) * entrance_boost
            intensity = max(0.1, min(1.0, intensity))

            # Apply pacing style curve
            if pacing_style == "fast":
                intensity = min(1.0, intensity * 1.2)
            elif pacing_style == "chill":
                intensity = max(0.1, intensity * 0.8)

            profile.append(round(intensity, 3))

        return profile

    def _compute_music_intensity(self, beats: list[StoryBeat], pacing: str):
        """Set music intensity per beat."""
        for beat in beats:
            base = {
                "hook": 0.8,
                "setup": 0.4,
                "rising_action": 0.6,
                "climax": 1.0,
                "twist": 0.85,
                "resolution": 0.5,
                "outro": 0.3,
            }.get(beat.beat_type, 0.5)

            if pacing == "fast":
                base = min(1.0, base * 1.15)
            elif pacing == "chill":
                base = max(0.1, base * 0.75)

            beat.music_intensity = round(base, 2)

    # ─── VO Suggestions ────────────────────────────────────

    def _generate_vo_suggestions(self, beats: list[StoryBeat]):
        """Generate voice-over text suggestions for each beat."""
        for i, beat in enumerate(beats):
            transcript = beat.transcript.strip()
            beat_type = beat.beat_type

            if not transcript:
                beat.vo_suggestion = self._vo_template(beat_type, i, len(beats))
                continue

            # Extract key phrase from transcript
            key_phrase = self._extract_key_phrase(transcript)

            # Build VO based on beat type and key phrase
            vo = self._build_vo_for_beat(beat_type, key_phrase, i, len(beats))
            beat.vo_suggestion = vo

    def _extract_key_phrase(self, transcript: str, max_len: int = 80) -> str:
        """Extract the most impactful phrase from transcript."""
        sentences = [s.strip() for s in transcript.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if not sentences:
            return transcript[:max_len]

        # Score each sentence
        scored = []
        for sent in sentences:
            score = 0
            # Length factor (not too short, not too long)
            score += min(len(sent) / 50, 1.0)
            # Excitement markers
            score += sent.count("!") * 0.3
            # Specific terms
            score += sum(1 for w in ["wichtig", "neu", "exklusiv", "breaking", "amazing"] if w in sent.lower()) * 0.2
            scored.append((score, sent))

        scored.sort(reverse=True)
        best = scored[0][1] if scored else sentences[0]
        return best[:max_len]

    def _build_vo_for_beat(self, beat_type: str, key_phrase: str, index: int, total: int) -> str:
        """Build VO suggestion for a specific beat type."""
        templates = {
            "hook": [
                "Das musst du sehen: {phrase}",
                "Was passiert hier? {phrase}",
                "Moment mal... {phrase}",
            ],
            "setup": [
                "Die Story: {phrase}",
                "Hintergrund: {phrase}",
                "Es begann so: {phrase}",
            ],
            "rising_action": [
                "Dann kam der Wendepunkt: {phrase}",
                "Aber das war noch nicht alles: {phrase}",
                "Spannung steigt: {phrase}",
            ],
            "climax": [
                "Der Höhepunkt: {phrase}",
                "Das musst du gesehen haben: {phrase}",
                "Hier kracht's: {phrase}",
            ],
            "twist": [
                "Plot Twist: {phrase}",
                "Aber warte: {phrase}",
                "Das Unerwartete: {phrase}",
            ],
            "resolution": [
                "Das Ergebnis: {phrase}",
                "Fazit: {phrase}",
                "Und das ist die Lösung: {phrase}",
            ],
            "outro": [
                "Folge uns für mehr!",
                "Mehr dazu auf W24.at",
                "Like & Share!",
            ],
        }

        tmpl_list = templates.get(beat_type, ["{phrase}"])
        tmpl = tmpl_list[index % len(tmpl_list)]

        if beat_type == "outro":
            return tmpl
        return tmpl.format(phrase=key_phrase)

    def _vo_template(self, beat_type: str, index: int, total: int) -> str:
        """Fallback VO template when no transcript available."""
        return {
            "hook": "Achtung — das kommt jetzt!",
            "setup": "Die Geschichte dahinter...",
            "rising_action": "Und dann passierte es...",
            "climax": "Der absolute Wahnsinn!",
            "twist": "Aber niemand sah das kommen...",
            "resolution": "Das ist das Ergebnis.",
            "outro": "Folge uns für mehr!",
        }.get(beat_type, "")

    # ─── Summary & Metadata ────────────────────────────────

    def _build_summary(self, beats: list[StoryBeat]) -> str:
        """Build a human-readable story summary."""
        if not beats:
            return "No story beats generated."

        parts = []
        total_dur = sum(b.duration for b in beats)

        parts.append(f"Story arc: {' → '.join(b.beat_type for b in beats)}")
        parts.append(f"Duration: {total_dur:.1f}s across {len(beats)} beats")

        for beat in beats:
            emoji = {
                "hook": "🎣",
                "setup": "📖",
                "rising_action": "📈",
                "climax": "🔥",
                "twist": "💥",
                "resolution": "✅",
                "outro": "👋",
            }.get(beat.beat_type, "➡️")

            vo_preview = beat.vo_suggestion[:60] if beat.vo_suggestion else ""
            vo_info = f' — "{vo_preview}"' if vo_preview else ""
            parts.append(
                f"  {emoji} {beat.beat_type:<16} Scene #{beat.scene_index} "
                f"({beat.duration:.1f}s, score={beat.score:.2f}){vo_info}"
            )

        return "\n".join(parts)

    def _generate_metadata(self, beats: list[StoryBeat], recipe: str) -> tuple:
        """Generate title and hashtag suggestions."""
        # Collect key terms from transcripts
        all_text = " ".join(b.transcript for b in beats if b.transcript)

        # Simple keyword extraction
        keywords = []
        for word in all_text.lower().split():
            word = word.strip(".,!?;:")
            if len(word) > 4 and word not in {
                "dass", "weil", "wenn", "dann", "aber", "oder", "und", "mit",
                "that", "with", "from", "this", "have", "were", "they",
            }:
                keywords.append(word)

        # Most common keywords
        from collections import Counter
        top_kw = Counter(keywords).most_common(3)
        top_terms = [k for k, _ in top_kw] if top_kw else ["video", "highlight"]

        # Title suggestion
        title = f"{' '.join(t.capitalize() for t in top_terms[:2])} — Must See"
        if recipe == "social_teaser_w24":
            title = f"🔥 {title}"

        # Hashtags
        hashtags = [f"#{t}" for t in top_terms[:3]]
        hashtags.extend(["#W24", "#Highlight", "#MustSee"])

        return title, hashtags

    # ─── Helpers ───────────────────────────────────────────

    def _get_template(self, recipe: str) -> dict:
        """Get story template for recipe."""
        if recipe in STORY_TEMPLATES:
            return STORY_TEMPLATES[recipe]

        # Default template
        return {
            "beats": ["hook", "setup", "rising_action", "climax", "resolution"],
            "target_duration": (30, 60),
            "scene_count": (4, 8),
            "pacing": "dynamic",
            "music_arc": "build_drop",
        }

    def _pick_target_duration(self, duration_range: tuple) -> float:
        """Pick a target duration from range."""
        min_dur, max_dur = duration_range
        # Target the middle, rounded to nearest 5
        target = round((min_dur + max_dur) / 2 / 5) * 5
        return max(min_dur, min(max_dur, target))


# ─── CLI Entry Point ────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Story Builder — Narrative Arc Engine for Video Kitchen"
    )
    parser.add_argument("--project-dir", required=True, help="Project directory")
    parser.add_argument("--recipe", default="social_teaser_w24", help="Recipe name")
    parser.add_argument("--target-duration", type=float, help="Target duration (seconds)")
    parser.add_argument("--min-score", type=float, default=0.15, help="Minimum scene score")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM enhancements")
    parser.add_argument("--output", default="storyboard.json", help="Output filename")

    args = parser.parse_args()

    # Load scenes
    scenes_path = Path(args.project_dir) / "scenes.json"
    if not scenes_path.exists():
        print(f"Error: No scenes.json found in {args.project_dir}")
        print("Run scoring.py first to analyze scenes.")
        sys.exit(1)

    with open(scenes_path) as f:
        scenes = json.load(f)

    print(f"[STORY] Building story from {len(scenes)} scenes...")
    print(f"[STORY] Recipe: {args.recipe}")

    builder = StoryBuilder(args.project_dir, llm_enabled=not args.no_llm)
    storyboard = builder.build(
        scenes=scenes,
        recipe=args.recipe,
        target_duration=args.target_duration,
        min_score=args.min_score,
    )

    builder.save(storyboard, args.output)

    print(f"\n{storyboard.story_summary}")
    print(f"\n[STORY] Title suggestion: {storyboard.title_suggestion}")
    print(f"[STORY] Hashtags: {' '.join(storyboard.hashtag_suggestions or [])}")


if __name__ == "__main__":
    main()
