#!/usr/bin/env python3
"""
prep_station.py — Scene Detection & Transcription for Video Kitchen v0.6.0

Stage 1 of the Video Kitchen pipeline. Detects scene boundaries using
PySceneDetect, extracts thumbnails, and optionally transcribes audio.

Usage:
    from prep_station import PrepStation
    prep = PrepStation(project_dir="/path/to/project")
    result = prep.process("video.mp4")

    # CLI:
    python3 prep_station.py video.mp4 --project-dir ./projects/my_proj
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

# Use PySceneDetect for reliable scene detection
from scenedetect import open_video, SceneManager, ContentDetector


class PrepStation:
    """Stage 1: Prep — detect scenes, extract thumbnails, transcribe."""

    def __init__(self, project_dir: str, thumbnail_width: int = 320):
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir = self.project_dir / "thumbnails"
        self.thumbnail_dir.mkdir(exist_ok=True)
        self.thumbnail_width = thumbnail_width

    def process(
        self,
        video_path: str,
        threshold: float = 27.0,
        min_scene_len: int = 15,
        extract_thumbs: bool = True,
        transcribe: bool = False,
        whisper_model: str = "base",
    ) -> dict:
        """
        Full prep pipeline: probe → detect scenes → thumbnails → optional transcript.

        Args:
            video_path: Path to source video
            threshold: PySceneDetect ContentDetector threshold (lower = more cuts)
            min_scene_len: Minimum scene length in frames
            extract_thumbs: Generate thumbnails
            transcribe: Run Whisper transcription
            whisper_model: Whisper model size

        Returns:
            dict with video_info, scenes, transcript (optional)
        """
        video_path = str(Path(video_path).resolve())
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        print(f"[PREP] Probing video: {video_path}")
        video_info = self._probe_video(video_path)

        print(f"[PREP] Detecting scenes (threshold={threshold})...")
        raw_scenes = self._detect_scenes(video_path, threshold, min_scene_len)

        print(f"[PREP] Found {len(raw_scenes)} scenes")
        scenes = self._build_scene_records(raw_scenes, video_info["duration"])

        if extract_thumbs:
            print(f"[PREP] Extracting {len(scenes)} thumbnails...")
            self._extract_thumbnails(video_path, scenes)

        transcript = None
        if transcribe:
            print(f"[PREP] Transcribing with Whisper ({whisper_model})...")
            transcript = self._transcribe(video_path, whisper_model)
            # Attach transcript segments to scenes
            self._assign_transcript_to_scenes(scenes, transcript)

        # Save results
        result = {
            "video_info": video_info,
            "scenes": scenes,
            "transcript": transcript,
        }

        scenes_path = self.project_dir / "scenes.json"
        with open(scenes_path, "w") as f:
            json.dump(scenes, f, indent=2, ensure_ascii=False)

        if transcript:
            with open(self.project_dir / "transcript.json", "w") as f:
                json.dump(transcript, f, indent=2, ensure_ascii=False)

        print(f"[PREP] Done. Scenes saved to {scenes_path}")
        return result

    def _probe_video(self, video_path: str) -> dict:
        """Get video metadata via ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next(
            (s for s in streams if s.get("codec_type") == "video"), {}
        )
        audio_stream = next(
            (s for s in streams if s.get("codec_type") == "audio"), None
        )

        # Parse frame rate
        fps = 0
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = r_frame_rate.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 0
        except (ValueError, ZeroDivisionError):
            pass

        return {
            "path": video_path,
            "duration": float(fmt.get("duration", 0)),
            "size": int(fmt.get("size", 0)),
            "bit_rate": int(fmt.get("bit_rate", 0)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "codec": video_stream.get("codec_name", ""),
            "fps": round(fps, 2),
            "has_audio": audio_stream is not None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        }

    def _detect_scenes(
        self, video_path: str, threshold: float, min_scene_len: int
    ) -> list[tuple[float, float]]:
        """Detect scene boundaries using PySceneDetect ContentDetector."""
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(
            ContentDetector(
                threshold=threshold,
                min_scene_len=min_scene_len,
            )
        )
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        # Convert to (start_seconds, end_seconds) tuples
        scenes = []
        for scene in scene_list:
            start_sec = scene[0].get_seconds()
            end_sec = scene[1].get_seconds()
            scenes.append((start_sec, end_sec))

        return scenes

    def _build_scene_records(
        self, raw_scenes: list[tuple[float, float]], total_duration: float
    ) -> list[dict]:
        """Build scene records with metadata."""
        records = []
        for i, (start, end) in enumerate(raw_scenes):
            duration = end - start
            thumb_path = str(self.thumbnail_dir / f"scene_{i + 1:03d}.jpg")
            records.append({
                "id": str(uuid.uuid4())[:8],
                "scene_index": i,
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "duration": round(duration, 3),
                "thumbnail": thumb_path,
                "visual_score": None,
                "transcript_score": None,
                "audio_score": None,
                "combined_score": None,
                "transcript": "",
                "labels": [],
                "selected": False,
            })
        return records

    def _extract_thumbnails(
        self, video_path: str, scenes: list[dict]
    ) -> None:
        """Extract a thumbnail at the midpoint of each scene."""
        for scene in scenes:
            mid = scene["start_time"] + (scene["duration"] / 2)
            thumb_path = scene["thumbnail"]

            cmd = [
                "ffmpeg", "-y", "-ss", str(mid),
                "-i", video_path,
                "-frames:v", "1",
                "-vf", f"scale={self.thumbnail_width}:-1",
                "-q:v", "3",
                thumb_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True)

    def _transcribe(self, video_path: str, model_size: str) -> dict:
        """Transcribe video using OpenAI Whisper API (via ffmpeg extraction)."""
        # Extract audio to temp WAV
        tmp_wav = self.project_dir / "_temp_audio.wav"
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(tmp_wav),
        ]
        subprocess.run(cmd, capture_output=True, text=True)

        # Try to use OpenAI API for transcription
        try:
            import openai
            client = openai.OpenAI()

            with open(tmp_wav, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            # Clean up temp file
            tmp_wav.unlink(missing_ok=True)

            segments = []
            for seg in getattr(response, "segments", []):
                # Handle both dict and object segment formats
                if isinstance(seg, dict):
                    start = seg.get("start", 0)
                    end = seg.get("end", 0)
                    text = seg.get("text", "").strip()
                else:
                    # Object format (OpenAI SDK v1.x)
                    start = getattr(seg, "start", 0)
                    end = getattr(seg, "end", 0)
                    text = getattr(seg, "text", "").strip()
                segments.append({
                    "start": start,
                    "end": end,
                    "text": text,
                })

            return {
                "text": getattr(response, "text", ""),
                "segments": segments,
                "language": getattr(response, "language", "unknown"),
                "duration": getattr(response, "duration", 0),
            }

        except Exception as e:
            # Fallback: try local whisper if available
            try:
                import whisper as local_whisper
                model = local_whisper.load_model(model_size)
                result = model.transcribe(str(tmp_wav))
                tmp_wav.unlink(missing_ok=True)

                segments = []
                for seg in result.get("segments", []):
                    segments.append({
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": seg["text"].strip(),
                    })

                return {
                    "text": result.get("text", ""),
                    "segments": segments,
                    "language": result.get("language", "unknown"),
                    "duration": result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0,
                }
            except ImportError:
                tmp_wav.unlink(missing_ok=True)
                return {
                    "text": "",
                    "segments": [],
                    "language": "unknown",
                    "duration": 0,
                    "error": f"Transcription failed: {e}",
                }

    def _assign_transcript_to_scenes(
        self, scenes: list[dict], transcript: Optional[dict]
    ) -> None:
        """Assign transcript segments to scenes based on time overlap."""
        if not transcript or not transcript.get("segments"):
            return

        for scene in scenes:
            scene_start = scene["start_time"]
            scene_end = scene["end_time"]
            texts = []
            for seg in transcript["segments"]:
                seg_start = seg["start"]
                seg_end = seg["end"]
                # Check overlap
                if seg_start < scene_end and seg_end > scene_start:
                    texts.append(seg["text"])
            scene["transcript"] = " ".join(texts).strip()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Prep Station — Scene Detection & Transcription"
    )
    parser.add_argument("video", help="Path to video file")
    parser.add_argument(
        "--project-dir", default="./projects/default",
        help="Project directory for output"
    )
    parser.add_argument("--threshold", type=float, default=27.0)
    parser.add_argument("--min-scene-len", type=int, default=15)
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--whisper-model", default="base")
    parser.add_argument("--no-thumbs", action="store_true")

    args = parser.parse_args()

    prep = PrepStation(args.project_dir)
    result = prep.process(
        video_path=args.video,
        threshold=args.threshold,
        min_scene_len=args.min_scene_len,
        extract_thumbs=not args.no_thumbs,
        transcribe=args.transcribe,
        whisper_model=args.whisper_model,
    )

    print(f"\n{'=' * 60}")
    print(f"Video: {result['video_info']['path']}")
    print(f"Duration: {result['video_info']['duration']:.1f}s")
    print(f"Resolution: {result['video_info']['width']}x{result['video_info']['height']}")
    print(f"Scenes detected: {len(result['scenes'])}")
    if result.get("transcript"):
        print(f"Transcript: {len(result['transcript'].get('segments', []))} segments")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
