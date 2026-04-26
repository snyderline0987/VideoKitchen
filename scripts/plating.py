#!/usr/bin/env python3
"""
plating.py — Video Assembly for Video Kitchen v0.6.0

Stage 4 of the Video Kitchen pipeline. Assembles selected scenes into
a final output video using MoviePy. Handles:
  - Scene clipping and concatenation
  - Aspect ratio conversion (face-safe crop for 9:16)
  - Transitions between scenes
  - Output in multiple formats

Usage:
    from plating import PlatingStation
    plate = PlatingStation(project_dir="/path/to/project")
    plate.assemble(video_path="video.mp4", scenes=[...], selection=[0,2,5], recipe={...})
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from moviepy import (
    VideoFileClip,
    concatenate_videoclips,
    ColorClip,
    TextClip,
    CompositeVideoClip,
    ImageClip,
)


class PlatingStation:
    """Stage 4: Plate — assemble final video from selected scenes."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.output_dir = self.project_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def assemble(
        self,
        video_path: str,
        scenes: list[dict],
        selection: list[int],
        recipe: dict,
        output_name: Optional[str] = None,
    ) -> dict:
        """
        Assemble selected scenes into a final video.

        Args:
            video_path: Source video
            scenes: All scene records (from scoring)
            selection: List of scene indices to include
            recipe: Recipe configuration
            output_name: Output filename (auto-generated if None)

        Returns:
            Output record dict
        """
        video_path = str(Path(video_path).resolve())
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        target_duration = recipe.get("target_duration", "30-60s")
        aspect_ratio = recipe.get("aspect_ratio", "16:9")
        transitions = recipe.get("transitions", "cut")

        # Parse target duration
        min_dur, max_dur = self._parse_duration_range(target_duration)
        print(f"[PLATE] Assembling {len(selection)} scenes for recipe '{recipe.get('name', 'custom')}'")
        print(f"[PLATE] Target: {min_dur}-{max_dur}s, aspect: {aspect_ratio}")

        # Load source video
        source = VideoFileClip(video_path)

        # Extract selected scenes
        clips = []
        total_duration = 0
        for scene_idx in selection:
            if scene_idx >= len(scenes):
                print(f"[PLATE] Warning: scene index {scene_idx} out of range, skipping")
                continue

            scene = scenes[scene_idx]
            start = scene["start_time"]
            end = scene["end_time"]

            # Trim if exceeding target duration
            remaining = max_dur - total_duration
            if remaining <= 0:
                break

            clip_dur = min(end - start, remaining)
            clip = source.subclipped(start, start + clip_dur)

            clips.append(clip)
            total_duration += clip_dur

        if not clips:
            raise ValueError("No valid scenes selected")

        print(f"[PLATE] Total clip duration: {total_duration:.1f}s ({len(clips)} clips)")

        # Apply transitions
        if transitions == "quick_cuts" and len(clips) > 1:
            # Quick cuts: no transition, direct concat with chain
            final = concatenate_videoclips(clips, method="chain")
        elif transitions == "crossfade" and len(clips) > 1:
            # Crossfade: 0.3s overlap via chain with padding
            final = concatenate_videoclips(
                clips, method="chain", padding=-0.3
            )
        else:
            final = concatenate_videoclips(clips, method="chain")

        # Aspect ratio conversion
        if aspect_ratio == "9:16":
            final = self._to_portrait(final, source, video_path)
        elif aspect_ratio == "1:1":
            final = self._to_square(final)

        # Generate output
        if output_name is None:
            output_name = f"output_{recipe.get('recipe', 'custom')}_{uuid.uuid4().hex[:6]}.mp4"

        output_path = self.output_dir / output_name

        print(f"[PLATE] Rendering to {output_path}...")
        final.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger=None,
        )

        # Clean up
        source.close()
        final.close()
        for clip in clips:
            clip.close()

        # Get output metadata
        output_info = self._probe_output(output_path)

        output_record = {
            "id": str(uuid.uuid4())[:8],
            "recipe_id": recipe.get("recipe", "custom"),
            "filename": output_name,
            "format": "mp4",
            "duration": output_info.get("duration", total_duration),
            "resolution": output_info.get("resolution", ""),
            "file_path": str(output_path),
            "file_size": output_info.get("size", 0),
            "qc_passed": None,
            "qc_report": None,
        }

        print(f"[PLATE] Done! Output: {output_path}")
        print(f"[PLATE] Duration: {output_record['duration']:.1f}s  "
              f"Size: {output_record['file_size'] / 1024:.0f}KB")

        return output_record

    def _parse_duration_range(self, duration_str: str) -> tuple[float, float]:
        """Parse duration range like '20-30s' into (min, max) seconds."""
        duration_str = duration_str.replace("s", "").strip()
        if "-" in duration_str:
            parts = duration_str.split("-")
            return float(parts[0]), float(parts[1])
        return float(duration_str), float(duration_str) * 1.5

    def _to_portrait(self, clip, source, video_path: str):
        """Convert to 9:16 portrait with face-safe blurred background."""
        target_w = 1080
        target_h = 1920

        # Resize clip to fit width
        resized = clip.resized(target_w / clip.w)

        # Create blurred background
        bg = source.subclipped(
            clip.start if hasattr(clip, 'start') else 0,
            min(clip.end if hasattr(clip, 'end') else source.duration, source.duration)
        ).resized(target_h / source.h)

        # Apply Gaussian blur to background
        # Note: MoviePy blur via filter
        try:
            from moviepy import vfx
            bg_blurred = bg.with_effects([vfx.GaussianBlur(sigma=20)])
        except (ImportError, Exception):
            bg_blurred = bg

        bg_cropped = bg_blurred.cropped(
            x_center=bg_blurred.w / 2,
            y_center=bg_blurred.h / 2,
            width=target_w,
            height=target_h,
        )

        # Center the resized clip on the blurred background
        final = CompositeVideoClip(
            [bg_cropped, resized.with_position("center")],
            size=(target_w, target_h),
        )

        return final

    def _to_square(self, clip):
        """Convert to 1:1 square by center-cropping."""
        target_size = min(clip.w, clip.h)
        return clip.cropped(
            x_center=clip.w / 2,
            y_center=clip.h / 2,
            width=target_size,
            height=target_size,
        )

    def _probe_output(self, path: Path) -> dict:
        """Get output file metadata."""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

        return {
            "duration": float(fmt.get("duration", 0)),
            "size": int(fmt.get("size", 0)),
            "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Plating Station — Video Assembly")
    parser.add_argument("video", help="Path to source video")
    parser.add_argument("--project-dir", default="./projects/default")
    parser.add_argument("--scenes", required=True, help="Comma-separated scene indices (0-based)")
    parser.add_argument("--recipe", default="spicy_trailer", help="Recipe name")
    parser.add_argument("--output", help="Output filename")

    args = parser.parse_args()

    # Load scenes
    scenes_path = Path(args.project_dir) / "scenes.json"
    with open(scenes_path) as f:
        scenes = json.load(f)

    # Parse selection
    selection = [int(x.strip()) for x in args.scenes.split(",")]

    # Load recipe
    recipe = {"recipe": args.recipe, "name": args.recipe, "target_duration": "30-60s", "aspect_ratio": "16:9"}

    plate = PlatingStation(args.project_dir)
    result = plate.assemble(
        video_path=args.video,
        scenes=scenes,
        selection=selection,
        recipe=recipe,
        output_name=args.output,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
