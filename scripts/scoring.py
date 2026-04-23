#!/usr/bin/env python3
"""
scoring.py — AI Scene Scoring Engine for Video Kitchen v0.6.0 (Sprint 2)

Stage 2 of the Video Kitchen pipeline. Multi-modal highlight detection:
  - OpenClip visual similarity scoring (action vs static scenes)
  - Whisper + LLM transcript analysis (dialogue peaks, keywords)
  - Audio energy scoring (RMS + dynamics)
  - Combined multi-modal scoring (visual 40% + audio 30% + transcript 30%)
  - Configurable scoring weights and thresholds
  - Top-N scene selection with minimum duration

Falls back gracefully when optional deps (open_clip, torch, cv2) are missing.

Usage:
    from scoring import ScoringEngine
    engine = ScoringEngine(project_dir="/path/to/project")
    engine.score(video_path="video.mp4", scenes=[...])
    top_n = engine.select_top_n(scenes, n=5, min_duration=2.0)

    # CLI:
    python3 scoring.py video.mp4 --project-dir ./projects/my_proj --top 5
"""

import json
import math
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

# Optional: OpenCV for frame-level visual analysis
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# Optional: OpenClip for visual similarity / action detection
try:
    import torch
    import open_clip
    from PIL import Image
    HAS_OPENCLIP = True
except ImportError:
    HAS_OPENCLIP = False


# ─── Default Configuration ──────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "visual": 0.40,
    "audio": 0.30,
    "transcript": 0.30,
}

DEFAULT_THRESHOLDS = {
    "min_score": 0.15,       # Minimum combined score to be considered a highlight
    "min_duration": 1.0,     # Minimum scene duration (seconds) for selection
    "action_similarity": 0.75,  # OpenClip cosine similarity threshold for "static"
}


class ScoringEngine:
    """Stage 2: Multi-modal AI scene scoring for highlight detection."""

    def __init__(
        self,
        project_dir: str,
        weights: Optional[dict] = None,
        thresholds: Optional[dict] = None,
    ):
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)

        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.thresholds = thresholds or dict(DEFAULT_THRESHOLDS)

        # Lazy-loaded models
        self._clip_model = None
        self._clip_preprocess = None
        self._clip_tokenizer = None

    # ─── Public API ────────────────────────────────────────

    def score(
        self,
        video_path: str,
        scenes: list[dict],
        weights: Optional[dict] = None,
        thresholds: Optional[dict] = None,
        use_llm: bool = True,
        use_openclip: bool = True,
    ) -> list[dict]:
        """
        Score all scenes and return updated scene records.

        Args:
            video_path: Path to source video
            scenes: List of scene dicts from prep_station
            weights: Override scoring weights {visual, audio, transcript}
            thresholds: Override scoring thresholds
            use_llm: Use LLM for transcript-based scoring
            use_openclip: Use OpenClip for visual similarity scoring

        Returns:
            Updated scenes list with scores and ranks
        """
        w = weights or self.weights
        t = thresholds or self.thresholds

        # Normalize weights
        total_w = sum(w.values())
        if total_w <= 0:
            raise ValueError(f"Weight sum must be > 0, got {total_w}")
        w = {k: v / total_w for k, v in w.items()}

        print(f"[SCORE] Scoring {len(scenes)} scenes...")
        print(f"[SCORE] Weights: visual={w['visual']:.2f}, "
              f"transcript={w['transcript']:.2f}, "
              f"audio={w['audio']:.2f}")
        print(f"[SCORE] Thresholds: min_score={t['min_score']}, "
              f"min_duration={t['min_duration']}s, "
              f"action_similarity={t['action_similarity']}")

        # ── Visual scoring ──
        if use_openclip and HAS_OPENCLIP:
            print("[SCORE] Computing OpenClip visual similarity scores...")
            visual_scores = self._openclip_visual_scores(video_path, scenes)
        elif HAS_CV2:
            print("[SCORE] Computing OpenCV visual scores (OpenClip unavailable)...")
            visual_scores = self._opencv_visual_scores(video_path, scenes)
        else:
            print("[SCORE] Computing thumbnail-based visual scores...")
            visual_scores = self._thumbnail_scores(scenes)

        # ── Transcript scoring ──
        print("[SCORE] Computing transcript scores...")
        transcript_scores = self._transcript_scores(scenes, use_llm=use_llm)

        # ── Audio energy scoring ──
        print("[SCORE] Computing audio energy scores...")
        audio_scores = self._audio_energy_scores(video_path, scenes)

        # ── Combine weighted scores ──
        print("[SCORE] Combining multi-modal scores...")
        for i, scene in enumerate(scenes):
            scene["visual_score"] = round(visual_scores[i], 4)
            scene["transcript_score"] = round(transcript_scores[i], 4)
            scene["audio_score"] = round(audio_scores[i], 4)

            combined = (
                w["visual"] * visual_scores[i]
                + w["transcript"] * transcript_scores[i]
                + w["audio"] * audio_scores[i]
            )
            scene["combined_score"] = round(combined, 4)

        # Assign ranks
        sorted_scenes = sorted(scenes, key=lambda s: s["combined_score"], reverse=True)
        for rank, scene in enumerate(sorted_scenes):
            scene["rank"] = rank + 1

        # Save
        self._save_scenes(scenes)

        # Print summary
        self._print_summary(sorted_scenes)

        return scenes

    def select_top_n(
        self,
        scenes: list[dict],
        n: int = 5,
        min_duration: Optional[float] = None,
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """
        Select top-N scenes by combined score with optional constraints.

        Args:
            scenes: Scored scene list (must have combined_score)
            n: Maximum number of scenes to return
            min_duration: Minimum scene duration in seconds
            min_score: Minimum combined score threshold

        Returns:
            List of top-N scene dicts, sorted by scene order (time)
        """
        min_dur = min_duration if min_duration is not None else self.thresholds["min_duration"]
        min_sc = min_score if min_score is not None else self.thresholds["min_score"]

        # Filter by thresholds
        candidates = [
            s for s in scenes
            if s.get("combined_score", 0) >= min_sc
            and s.get("duration", 0) >= min_dur
        ]

        # Sort by score descending, take top N
        candidates.sort(key=lambda s: s.get("combined_score", 0), reverse=True)
        selected = candidates[:n]

        # Sort by time order for output
        selected.sort(key=lambda s: s.get("scene_index", 0))

        total_dur = sum(s.get("duration", 0) for s in selected)
        print(f"[SCORE] Selected top {len(selected)} scenes "
              f"(total duration: {total_dur:.1f}s, "
              f"min_score={min_sc}, min_duration={min_dur}s)")

        return selected

    def analyze(
        self,
        video_path: str,
        scenes: list[dict],
        top_n: int = 5,
        **kwargs,
    ) -> dict:
        """
        Full analysis: score + select top-N.
        Convenience method for kitchen.py --analyze --top N.

        Args:
            video_path: Path to source video
            scenes: Scene list from prep_station
            top_n: Number of top scenes to select
            **kwargs: Passed to score()

        Returns:
            dict with 'scenes' (all scored) and 'highlights' (top-N)
        """
        scored = self.score(video_path, scenes, **kwargs)
        highlights = self.select_top_n(scored, n=top_n)

        return {
            "scenes": scored,
            "highlights": highlights,
            "highlight_indices": [s["scene_index"] for s in highlights],
        }

    # ─── OpenClip Visual Scoring ───────────────────────────

    def _load_clip(self):
        """Lazy-load OpenClip model, tokenizer, and preprocess."""
        if self._clip_model is not None:
            return

        if not HAS_OPENCLIP:
            raise RuntimeError("open_clip / torch not available")

        print("[SCORE] Loading OpenClip model (ViT-B-32/laion2b_s34b_b79k)...")
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        model.eval()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")

        self._clip_model = model
        self._clip_preprocess = preprocess
        self._clip_tokenizer = tokenizer
        print("[SCORE] OpenClip model loaded.")

    def _openclip_visual_scores(
        self, video_path: str, scenes: list[dict]
    ) -> list[float]:
        """
        Score scenes using OpenClip visual similarity.

        Strategy:
          1. Extract sample frames from each scene
          2. Compute CLIP embeddings for each frame
          3. Measure inter-frame cosine distance within scene (action indicator)
          4. Compare frames against "action" and "static" text prompts
          5. Combine: motion diversity + action-semantic similarity
        """
        self._load_clip()
        model = self._clip_model
        preprocess = self._clip_preprocess
        tokenizer = self._clip_tokenizer

        # Pre-compute text embeddings for action vs static
        with torch.no_grad():
            action_tokens = tokenizer(["action scene, dynamic, movement, people doing things"])
            static_tokens = tokenizer(["static scene, still, calm, no movement, landscape"])
            action_emb = model.encode_text(action_tokens)
            static_emb = model.encode_text(static_tokens)
            action_emb = action_emb / action_emb.norm(dim=-1, keepdim=True)
            static_emb = static_emb / static_emb.norm(dim=-1, keepdim=True)

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        scores = []

        for scene in scenes:
            start_frame = int(scene["start_time"] * fps)
            end_frame = int(scene["end_time"] * fps)

            # Sample frames
            sample_count = min(5, max(2, (end_frame - start_frame) // max(1, int(fps))))
            frame_embeddings = []

            for j in range(sample_count):
                frame_num = start_frame + j * max(1, (end_frame - start_frame) // sample_count)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Convert BGR → RGB PIL Image
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)

                with torch.no_grad():
                    image_input = preprocess(pil_img).unsqueeze(0)
                    emb = model.encode_image(image_input)
                    emb = emb / emb.norm(dim=-1, keepdim=True)
                    frame_embeddings.append(emb)

            if not frame_embeddings:
                scores.append(0.3)
                continue

            # Stack embeddings: [n_frames, dim]
            all_embs = torch.cat(frame_embeddings, dim=0)

            # Metric 1: Inter-frame visual diversity (cosine distance)
            # High diversity = action/interesting, low = static/boring
            if len(frame_embeddings) > 1:
                cos_sims = []
                for j in range(1, len(frame_embeddings)):
                    sim = torch.nn.functional.cosine_similarity(
                        frame_embeddings[j - 1], frame_embeddings[j]
                    ).item()
                    cos_sims.append(sim)
                avg_similarity = np.mean(cos_sims)
                # Lower similarity → more visual change → more interesting
                motion_diversity = 1.0 - avg_similarity
            else:
                motion_diversity = 0.3

            # Metric 2: Action vs static semantic score
            # Average embedding across all frames
            mean_emb = all_embs.mean(dim=0, keepdim=True)
            mean_emb = mean_emb / mean_emb.norm(dim=-1, keepdim=True)

            with torch.no_grad():
                action_sim = torch.nn.functional.cosine_similarity(
                    mean_emb, action_emb
                ).item()
                static_sim = torch.nn.functional.cosine_similarity(
                    mean_emb, static_emb
                ).item()

            # Normalize: how much more "action-like" than "static-like"
            semantic_score = (action_sim - static_sim + 1.0) / 2.0  # Map to [0, 1]

            # Combine metrics
            visual_score = 0.5 * min(motion_diversity * 2.5, 1.0) + 0.5 * semantic_score
            scores.append(max(0.0, min(1.0, visual_score)))

        cap.release()
        return scores

    # ─── OpenCV Visual Scoring (fallback) ──────────────────

    def _opencv_visual_scores(
        self, video_path: str, scenes: list[dict]
    ) -> list[float]:
        """
        Compute visual interest scores using OpenCV.
        Based on: motion energy, edge density, color variance, brightness.
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        scores = []

        for scene in scenes:
            start_frame = int(scene["start_time"] * fps)
            end_frame = int(scene["end_time"] * fps)

            # Sample frames from the scene
            sample_frames = []
            sample_count = min(5, max(1, (end_frame - start_frame) // max(1, int(fps))))
            for j in range(sample_count):
                frame_num = start_frame + j * max(1, (end_frame - start_frame) // sample_count)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret:
                    sample_frames.append(frame)

            if not sample_frames:
                scores.append(0.3)
                continue

            # Metric 1: Color variance (diversity of visual content)
            color_variances = []
            for frame in sample_frames:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                h_var = np.var(hsv[:, :, 0]) / (180 ** 2)
                s_var = np.var(hsv[:, :, 1]) / (255 ** 2)
                color_variances.append(h_var + s_var)
            avg_color_var = np.mean(color_variances) if color_variances else 0

            # Metric 2: Edge density (visual complexity)
            edge_densities = []
            for frame in sample_frames:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
                edge_densities.append(edge_density)
            avg_edge = np.mean(edge_densities) if edge_densities else 0

            # Metric 3: Motion energy (difference between consecutive frames)
            motion_scores = []
            for j in range(1, len(sample_frames)):
                diff = cv2.absdiff(
                    cv2.cvtColor(sample_frames[j], cv2.COLOR_BGR2GRAY),
                    cv2.cvtColor(sample_frames[j - 1], cv2.COLOR_BGR2GRAY),
                )
                motion = np.mean(diff) / 255.0
                motion_scores.append(motion)
            avg_motion = np.mean(motion_scores) if motion_scores else 0.1

            # Metric 4: Brightness (avoid too dark/bright scenes)
            brightness = np.mean([np.mean(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)) / 255.0
                                  for f in sample_frames])
            brightness_score = 1.0 - abs(brightness - 0.5) * 2

            # Combine visual metrics
            visual_score = (
                0.25 * min(avg_color_var * 5, 1.0)
                + 0.30 * min(avg_edge * 3, 1.0)
                + 0.25 * min(avg_motion * 3, 1.0)
                + 0.20 * brightness_score
            )
            scores.append(max(0.0, min(1.0, visual_score)))

        cap.release()
        return scores

    # ─── Thumbnail Visual Scoring (minimal fallback) ───────

    def _thumbnail_scores(self, scenes: list[dict]) -> list[float]:
        """
        Fallback visual scoring using thumbnail analysis.
        Used when neither OpenClip nor OpenCV is available.
        """
        scores = []
        for scene in scenes:
            thumb_path = scene.get("thumbnail", "")
            if not thumb_path or not os.path.exists(thumb_path):
                scores.append(0.5)
                continue

            try:
                from PIL import Image
                img = Image.open(thumb_path).convert("RGB")
                arr = np.array(img)

                # Color variance
                color_var = np.var(arr) / (255 ** 2)

                # Edge proxy: standard deviation of pixel differences
                dx = np.diff(arr, axis=1)
                dy = np.diff(arr, axis=0)
                edge_proxy = (np.std(dx) + np.std(dy)) / (2 * 255)

                score = 0.5 * min(color_var * 10, 1.0) + 0.5 * min(edge_proxy * 5, 1.0)
                scores.append(max(0.1, min(1.0, score)))
            except Exception:
                scores.append(0.5)

        return scores

    # ─── Transcript Scoring ────────────────────────────────

    def _transcript_scores(
        self, scenes: list[dict], use_llm: bool = True
    ) -> list[float]:
        """
        Score scenes based on transcript content.
        Uses LLM for semantic scoring (dialogue peaks, keywords), falls back to heuristics.
        """
        has_transcripts = any(s.get("transcript", "").strip() for s in scenes)

        if not has_transcripts:
            return [0.5] * len(scenes)

        if use_llm:
            try:
                return self._llm_transcript_scores(scenes)
            except Exception as e:
                print(f"[SCORE] LLM scoring failed ({e}), using heuristics")

        return self._heuristic_transcript_scores(scenes)

    def _llm_transcript_scores(self, scenes: list[dict]) -> list[float]:
        """
        Use LLM to score transcript for dialogue peaks and keyword relevance.

        The LLM evaluates each scene for:
        - Dialogue intensity (peaks, emotional moments)
        - Keyword relevance (topic-bearing terms)
        - Quotability (sound-bite potential)
        """
        import openai
        client = openai.OpenAI()

        # Batch scenes for efficiency
        scene_texts = []
        for scene in scenes:
            text = scene.get("transcript", "").strip()
            scene_texts.append(f"Scene {scene['scene_index']}: {text or '(no speech)'}")

        prompt = (
            "You are scoring video scenes for highlight potential based on their transcripts.\n"
            "Evaluate each scene for:\n"
            "- Dialogue peaks: emotional intensity, tension, humor, revelation\n"
            "- Keyword density: topic-relevant terms, proper nouns, specific claims\n"
            "- Quotability: sound-bite potential, memorable phrases\n\n"
            "Rate each scene from 0.0 to 1.0 where:\n"
            "- 1.0 = peak highlight (emotional climax, key revelation, quotable moment)\n"
            "- 0.5 = average (routine dialogue, filler, transitional)\n"
            "- 0.0 = skip (silence, dead air, noise, unintelligible)\n\n"
            "Respond ONLY with a JSON array of floats, one per scene.\n"
            f"Example: [0.8, 0.3, 0.9, 0.5]\n\n"
            f"Scenes:\n" + "\n".join(scene_texts)
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )

        content = response.choices[0].message.content.strip()
        # Handle markdown code blocks
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        scores_raw = json.loads(content)
        if not isinstance(scores_raw, list) or len(scores_raw) != len(scenes):
            raise ValueError("LLM returned invalid score format")

        return [max(0.0, min(1.0, float(s))) for s in scores_raw]

    def _heuristic_transcript_scores(self, scenes: list[dict]) -> list[float]:
        """Heuristic transcript scoring: keyword density, excitement, length."""
        scores = []
        for scene in scenes:
            text = scene.get("transcript", "").strip()
            if not text:
                scores.append(0.2)
                continue

            # Length score
            length_score = min(len(text) / 200, 1.0)

            # Excitement score (questions, exclamations)
            excitement = text.count("?") + text.count("!")
            excitement_score = min(excitement / 3, 1.0)

            # Keyword score (highlight indicators)
            highlight_words = [
                "neu", "exklusiv", "wichtig", "sensationell", "brechting",
                "überraschend", "erstaunlich", "unglaublich", "besonders",
                "new", "exclusive", "breaking", "amazing", "incredible",
                "surprising", "important", "special", "best", "worst",
                "first", "never", "always", "love", "hate", "wow",
                "discover", "reveal", "announce", "launch", "win",
            ]
            text_lower = text.lower()
            keyword_count = sum(1 for w in highlight_words if w in text_lower)
            keyword_score = min(keyword_count / 3, 1.0)

            score = 0.4 * length_score + 0.3 * excitement_score + 0.3 * keyword_score
            scores.append(max(0.1, min(1.0, score)))

        return scores

    # ─── Audio Energy Scoring ──────────────────────────────

    def _audio_energy_scores(
        self, video_path: str, scenes: list[dict]
    ) -> list[float]:
        """Score scenes based on audio energy and dynamics."""
        scores = []

        for scene in scenes:
            duration = scene["duration"]
            if duration < 0.5:
                scores.append(0.3)
                continue

            start = scene["start_time"]
            tmp_wav = self.project_dir / f"_temp_audio_{scene['scene_index']}.wav"

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", video_path,
                "-t", str(min(duration, 30)),
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "8000", "-ac", "1",
                str(tmp_wav),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0 or not tmp_wav.exists():
                scores.append(0.3)
                continue

            try:
                with open(tmp_wav, "rb") as f:
                    f.read(44)  # Skip WAV header
                    raw = f.read()

                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                samples = samples / 32768.0

                if len(samples) == 0:
                    scores.append(0.2)
                    continue

                # RMS energy
                rms = np.sqrt(np.mean(samples ** 2))

                # Dynamic range (std of windowed energy)
                window_size = min(8000, len(samples) // 4)
                if window_size > 0:
                    windows = np.array_split(samples, max(1, len(samples) // window_size))
                    window_energies = [np.sqrt(np.mean(w ** 2)) for w in windows]
                    dynamics = np.std(window_energies)
                else:
                    dynamics = 0

                rms_score = min(rms * 5, 1.0)
                dynamics_score = min(dynamics * 10, 1.0)
                score = 0.6 * rms_score + 0.4 * dynamics_score
                scores.append(max(0.1, min(1.0, score)))

            except Exception:
                scores.append(0.3)
            finally:
                tmp_wav.unlink(missing_ok=True)

        return scores

    # ─── Persistence ───────────────────────────────────────

    @staticmethod
    def _convert_numpy(obj):
        """Convert numpy types to native Python for JSON serialization."""
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    def _save_scenes(self, scenes: list[dict]) -> None:
        """Save scored scenes to project directory."""
        import numpy as np
        # Sanitize numpy types
        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(v) for v in obj]
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj
        output_path = self.project_dir / "scenes.json"
        with open(output_path, "w") as f:
            json.dump(sanitize(scenes), f, indent=2, ensure_ascii=False)
        print(f"[SCORE] Scored scenes saved to {output_path}")

    def _print_summary(self, sorted_scenes: list[dict]) -> None:
        """Print top-scene summary."""
        top5 = sorted_scenes[:5]
        print(f"\n[SCORE] Top {min(5, len(top5))} highlights:")
        for s in top5:
            idx = s["scene_index"]
            score = s["combined_score"]
            dur = s["duration"]
            txt = s.get("transcript", "")[:50]
            print(f"  Scene {idx}: score={score:.3f}  dur={dur:.1f}s  "
                  f"vis={s['visual_score']:.3f} txt={s['transcript_score']:.3f} "
                  f"aud={s['audio_score']:.3f}  \"{txt}\"")


# ─── CLI Entry Point ────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Scoring Engine — AI Multi-Modal Scene Scoring"
    )
    parser.add_argument("video", help="Path to video file")
    parser.add_argument(
        "--project-dir", default="./projects/default",
        help="Project directory"
    )
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM scoring")
    parser.add_argument("--no-openclip", action="store_true", help="Skip OpenClip scoring")
    parser.add_argument(
        "--weights", default="0.4,0.3,0.3",
        help="Weights: visual,transcript,audio (default: 0.4,0.3,0.3)"
    )
    parser.add_argument(
        "--top", type=int, default=0,
        help="Select top-N highlights after scoring"
    )
    parser.add_argument(
        "--min-duration", type=float, default=1.0,
        help="Minimum scene duration for top-N selection"
    )
    parser.add_argument(
        "--min-score", type=float, default=0.15,
        help="Minimum combined score for top-N selection"
    )

    args = parser.parse_args()

    # Load scenes from project
    project_dir = Path(args.project_dir)
    scenes_path = project_dir / "scenes.json"
    if not scenes_path.exists():
        print(f"Error: No scenes.json found in {args.project_dir}")
        print("Run prep_station.py first to detect scenes.")
        sys.exit(1)

    with open(scenes_path) as f:
        scenes = json.load(f)

    # Parse weights
    w_parts = [float(x) for x in args.weights.split(",")]
    weights = {"visual": w_parts[0], "transcript": w_parts[1], "audio": w_parts[2]}

    thresholds = {
        "min_score": args.min_score,
        "min_duration": args.min_duration,
        "action_similarity": 0.75,
    }

    engine = ScoringEngine(
        args.project_dir,
        weights=weights,
        thresholds=thresholds,
    )

    if args.top > 0:
        # Full analysis: score + select top-N
        result = engine.analyze(
            video_path=args.video,
            scenes=scenes,
            top_n=args.top,
            use_llm=not args.no_llm,
            use_openclip=not args.no_openclip,
        )
        print(f"\n[SCORE] Top {args.top} highlight indices: {result['highlight_indices']}")
    else:
        # Score only
        engine.score(
            video_path=args.video,
            scenes=scenes,
            use_llm=not args.no_llm,
            use_openclip=not args.no_openclip,
        )


if __name__ == "__main__":
    main()
