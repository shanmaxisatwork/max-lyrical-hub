#!/usr/bin/env python3
"""
STEP 2: Download videos using yt-dlp
- Talks directly to YouTube internal API — no middleman site
- No Cloudflare, no IP blocks, works perfectly on GitHub Actions
- Downloads best quality (1080p video + best audio, auto-merged)
- Extracts original thumbnail automatically
- Sends Telegram status at every step
"""

import os
import json
import time
import requests
import yt_dlp
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
QUEUE_FILE         = "state/download_queue.json"
DOWNLOADS_DIR      = "downloads"

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
        }, timeout=10)
    except Exception as e:
        print(f"  [TELEGRAM ERROR] {e}")

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def download_thumbnail(url, video_id):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            path = f"{DOWNLOADS_DIR}/{video_id}_thumbnail.jpg"
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"  thumbnail saved: {path}")
            return path
    except Exception as e:
        print(f"  thumbnail failed: {e}")
    return None

# ─── YT-DLP DOWNLOADER ────────────────────────────────────────────────────────
def download_video(video_id, title):
    """
    Download YouTube video using yt-dlp.
    - Best video (max 1080p) + best audio, auto-merged into MP4
    - No cookies, no login, no third-party site
    - Works directly with YouTube's internal API
    """
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True)
    safe  = "".join(c for c in title if c.isalnum() or c in " -_")[:50].strip()
    out   = f"{DOWNLOADS_DIR}/{video_id}_{safe}.mp4"
    url   = f"https://www.youtube.com/watch?v={video_id}"

    # Progress hook — logs every 25%
    last_pct = {"v": 0}
    def progress_hook(d):
        if d["status"] == "downloading":
            total   = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            dled    = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (dled / total) * 100
                if pct - last_pct["v"] >= 25:
                    print(f"     {pct:.0f}% — {dled//1024//1024}MB / {total//1024//1024}MB")
                    last_pct["v"] = pct
        elif d["status"] == "finished":
            print(f"  download finished, merging streams...")

    ydl_opts = {
        # Best video (up to 1080p) + best audio → merged into single mp4
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
        "outtmpl": out,
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],

        # Speed + reliability settings
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,

        # Avoid bot detection
        "sleep_interval": 1,
        "max_sleep_interval": 3,

        # No extra files
        "noplaylist": True,
        "no_warnings": False,
        "quiet": False,
        "noprogress": False,

        # FFmpeg for merging
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    print(f"  yt-dlp downloading: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # yt-dlp sometimes adds .mp4.mp4 — find the actual output file
    if not os.path.exists(out):
        # Search for the file
        candidates = list(Path(DOWNLOADS_DIR).glob(f"{video_id}*.mp4"))
        if candidates:
            actual = str(candidates[0])
            print(f"  file found at: {actual}")
            return actual
        raise Exception("Output file not found after yt-dlp download")

    size = os.path.getsize(out) / (1024 * 1024)
    if size < 1:
        raise Exception(f"Output file too small: {size:.1f}MB — download likely failed")

    print(f"  SUCCESS: {size:.1f} MB → {out}")
    return out

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Downloader (yt-dlp)")
    print(f"{'='*60}\n")

    queue       = load_json(QUEUE_FILE, [])
    to_download = [v for v in queue if v.get("status") == "queued"]

    if not to_download:
        print("no videos in queue.")
        telegram("Downloader: No videos queued — skipping.")
        return

    print(f"{len(to_download)} video(s) to download\n")
    telegram(
        f"Download Started!\n"
        f"{len(to_download)} video(s) via yt-dlp\n"
        f"Downloading directly from YouTube..."
    )

    for v in to_download:
        vid_id = v["id"]
        title  = v["title"]
        mins   = v.get("duration_s", 0) // 60

        print(f"\n{'─'*50}")
        print(f"Downloading: {title[:70]}")
        print(f"Duration: {mins}m | Views: {v.get('views', 0):,}")

        telegram(
            f"Downloading #{v.get('rank','?')}\n"
            f"{title[:60]}\n"
            f"{mins} min | {v.get('views',0):,} views\n"
            f"Starting yt-dlp..."
        )

        # Download thumbnail from YouTube directly
        thumb_path = download_thumbnail(v.get("thumbnail_url", ""), vid_id)

        try:
            video_path = download_video(vid_id, title)
            file_size  = os.path.getsize(video_path) / (1024 * 1024)

            for item in queue:
                if item["id"] == vid_id:
                    item["status"]         = "downloaded"
                    item["video_path"]     = video_path
                    item["thumbnail_path"] = thumb_path
                    break

            save_json(QUEUE_FILE, queue)

            telegram(
                f"Download Complete!\n"
                f"{title[:60]}\n"
                f"Size: {file_size:.1f} MB\n"
                f"Thumbnail: {'saved' if thumb_path else 'not found'}\n"
                f"Next: Adding watermark..."
            )
            print(f"SUCCESS! {file_size:.1f} MB")

        except Exception as e:
            err = str(e)[:200]
            print(f"FAILED: {err}")

            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "download_failed"
                    item["error"]  = err
                    break

            save_json(QUEUE_FILE, queue)
            telegram(
                f"Download FAILED\n"
                f"{title[:50]}\n"
                f"Error: {err[:150]}"
            )

        time.sleep(2)

    done   = sum(1 for v in queue if v.get("status") == "downloaded")
    failed = sum(1 for v in to_download if v.get("status") == "download_failed")

    print(f"\nDone: {done} success, {failed} failed")
    telegram(
        f"Download Phase Done!\n"
        f"Success: {done} | Failed: {failed}\n"
        f"Next: Watermark processing..."
    )

if __name__ == "__main__":
    main()
