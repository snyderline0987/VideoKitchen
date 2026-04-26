#!/usr/bin/env python3
"""
w24.py — W24 Video API Integration for FFWD Kitchen

Download videos, fetch metadata, and resolve stream URLs from W24.at

Usage:
    python3 scripts/w24.py download --video 37331 --output projects/rapid392/source.mp4
    python3 scripts/w24.py info --video 37331
    python3 scripts/w24.py resolve --video 37331
"""
import argparse, json, os, re, subprocess, sys
from html import unescape
from urllib.request import urlopen, Request

W24_BASE = "https://www.w24.at"
VOD_SERVER = "ms01.w24.at"
VOD_SERVER_ALT = "ms02.w24.at"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch_page(url):
    """Fetch page HTML."""
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def get_video_data(video_id):
    """Extract video metadata from W24 page HTML."""
    import requests
    url = f"{W24_BASE}/Sendungen-A-Z?video={video_id}"
    
    # Try to find the video on any show page — we need to construct the right URL
    # First try a generic approach: search for the data-video in any page
    # The video ID appears in data-video attributes
    html = requests.get(url, headers=HEADERS, timeout=15).text
    
    # Find all data-video entries
    blocks = re.findall(r"data-video='([^']+)'", html)
    for block in blocks:
        decoded = unescape(block)
        try:
            d = json.loads(decoded)
            if d.get("id") == video_id:
                return d
        except json.JSONDecodeError:
            continue
    
    # If not found on generic page, we might need the specific show URL
    # Try fetching from the page that contains it
    # Look for the show URL pattern
    return None


def get_video_data_from_url(page_url, video_id):
    """Extract video metadata from a specific W24 page URL."""
    import requests
    html = requests.get(page_url, headers=HEADERS, timeout=15).text
    blocks = re.findall(r"data-video='([^']+)'", html)
    for block in blocks:
        decoded = unescape(block)
        try:
            d = json.loads(decoded)
            if d.get("id") == video_id:
                return d
        except json.JSONDecodeError:
            continue
    # If video_id not matched, return first entry
    for block in blocks:
        decoded = unescape(block)
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            continue
    return None


def get_mp4_url(id_production, server=VOD_SERVER):
    """Build direct MP4 download URL."""
    return f"https://{server}/vod/w24/{id_production}_H.mp4"


def get_hls_url(id_production, server=VOD_SERVER):
    """Build HLS stream URL."""
    return f"https://{server}/vodw24/smil:{id_production}.smil/playlist.m3u8"


def download_video(video_id, output_path, page_url=None):
    """Download a W24 video by its ID."""
    print(f"🍳 W24 Download: video={video_id}")
    
    # Get metadata
    if page_url:
        data = get_video_data_from_url(page_url, video_id)
    else:
        data = get_video_data(video_id)
    
    if not data:
        print("  ERROR: Could not resolve video metadata.")
        print("  Try providing the full page URL with --url")
        return False
    
    id_prod = data.get("idProduction")
    title = data.get("title", "Unknown")
    
    if not id_prod:
        print("  ERROR: No idProduction found in metadata.")
        return False
    
    print(f"  Title: {title}")
    print(f"  Production ID: {id_prod}")
    
    # Build download URL
    mp4_url = get_mp4_url(id_prod)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # Download with curl (faster than Python for large files)
    print(f"  Downloading: {mp4_url}")
    r = subprocess.run(
        f"curl -L -o '{output_path}' '{mp4_url}' 2>&1",
        shell=True, capture_output=True, text=True, timeout=300
    )
    
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"  ✅ Downloaded: {size_mb:.0f}MB → {output_path}")
        
        # Save metadata alongside
        meta_path = os.path.join(os.path.dirname(output_path), "w24_meta.json")
        with open(meta_path, "w") as f:
            json.dump({
                "video_id": video_id,
                "idProduction": id_prod,
                "title": title,
                "sendungVom": data.get("sendungVom"),
                "mp4_url": mp4_url,
                "hls_url": get_hls_url(id_prod),
                "downloaded_at": __import__("datetime").datetime.now().isoformat(),
            }, f, indent=2)
        return True
    else:
        print(f"  ❌ Download failed.")
        return False


def show_info(video_id, page_url=None):
    """Show video metadata."""
    if page_url:
        data = get_video_data_from_url(page_url, video_id)
    else:
        data = get_video_data(video_id)
    
    if not data:
        print(f"No data found for video {video_id}")
        return
    
    print(f"  ID:            {data.get('id')}")
    print(f"  Title:         {data.get('title')}")
    print(f"  Production:    {data.get('idProduction')}")
    print(f"  Sendung vom:   {data.get('sendungVom')}")
    print(f"  MP4:           {get_mp4_url(data.get('idProduction',''))}")
    print(f"  HLS:           {get_hls_url(data.get('idProduction',''))}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="W24 Video API")
    sub = p.add_subparsers(dest="action")
    
    dl = sub.add_parser("download", help="Download video")
    dl.add_argument("--video", type=int, required=True, help="W24 video ID")
    dl.add_argument("--output", required=True, help="Output file path")
    dl.add_argument("--url", help="Full W24 page URL (if known)")
    
    info = sub.add_parser("info", help="Show video info")
    info.add_argument("--video", type=int, required=True)
    info.add_argument("--url", help="Full W24 page URL")
    
    resolve = sub.add_parser("resolve", help="Resolve stream URLs")
    resolve.add_argument("--video", type=int, required=True)
    resolve.add_argument("--url", help="Full W24 page URL")
    
    args = p.parse_args()
    
    if args.action == "download":
        download_video(args.video, args.output, args.url)
    elif args.action == "info":
        show_info(args.video, args.url)
    elif args.action == "resolve":
        show_info(args.video, args.url)
    else:
        p.print_help()
