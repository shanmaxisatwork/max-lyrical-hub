#!/usr/bin/env python3
"""
STEP 2: Download videos using Invidious API
- No browser, no Playwright, no Cloudflare issues
- Uses 15+ public Invidious instances with auto-fallback
- Gets direct MP4 download URL for best quality (1080p → 720p → best)
- Downloads video + audio streams and merges with FFmpeg if needed
- Downloads original thumbnail
- Sends Telegram status at every step
"""

import os
import json
import time
import requests
import subprocess
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
QUEUE_FILE         = "state/download_queue.json"
DOWNLOADS_DIR      = "downloads"

# 15+ public Invidious instances — tried in order, auto-fallback if one fails
INVIDIOUS_INSTANCES = [
    "https://invidious.nerdvpn.de",
    "https://invidious.privacydev.net",
    "https://inv.tux.pizza",
    "https://invidious.fdn.fr",
    "https://invidious.lunar.icu",
    "https://invidious.dhusch.de",
    "https://vid.puffyan.us",
    "https://yt.cdaut.de",
    "https://invidious.osi.kr",
    "https://invidious.io.lol",
    "https://invidious.protokolla.fi",
    "https://iv.melmac.space",
    "https://invidious.perennialte.ch",
    "https://yt.artemislena.eu",
    "https://invidious.flokinet.to",
]

QUALITY_PRIORITY = ["1080", "720", "480", "360"]

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    clean = msg.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","")
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean}, timeout=10)
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

def download_file(url, output_path, desc="file", timeout=600):
    """Stream-download a file with progress logging every 25%."""
    print(f"  downloading {desc}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.youtube.com/",
    }
    try:
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            total      = int(r.headers.get("content-length", 0))
            downloaded = 0
            last_log   = 0
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = (downloaded / total) * 100
                            if pct - last_log >= 25:
                                print(f"     {pct:.0f}% — {downloaded//1024//1024}MB / {total//1024//1024}MB")
                                last_log = pct
        size_mb = os.path.getsize(output_path) / (1024*1024)
        print(f"  saved: {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"  download_file failed: {e}")
        return False

def download_thumbnail(url, video_id):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            path = f"{DOWNLOADS_DIR}/{video_id}_thumbnail.jpg"
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"  thumbnail saved")
            return path
    except Exception as e:
        print(f"  thumbnail failed: {e}")
    return None

# ─── INVIDIOUS API ────────────────────────────────────────────────────────────
def get_video_info(video_id):
    """Try each Invidious instance until one works."""
    for instance in INVIDIOUS_INSTANCES:
        url = f"{instance}/api/v1/videos/{video_id}"
        try:
            print(f"  trying {instance} ...")
            r = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"
            })
            if r.status_code == 200:
                data = r.json()
                if data.get("formatStreams") or data.get("adaptiveFormats"):
                    print(f"  got video info!")
                    return instance, data
                else:
                    print(f"  empty formats from {instance}")
            else:
                print(f"  HTTP {r.status_code} from {instance}")
        except requests.Timeout:
            print(f"  timeout: {instance}")
        except Exception as e:
            print(f"  error {instance}: {str(e)[:60]}")
        time.sleep(0.5)
    return None, None

def pick_best_stream(video_data, instance_url):
    """
    Pick best quality stream.
    adaptiveFormats = separate video+audio (up to 1080p) — need FFmpeg merge
    formatStreams   = combined video+audio (up to 720p)   — direct download
    """
    format_streams   = video_data.get("formatStreams", [])
    adaptive_formats = video_data.get("adaptiveFormats", [])

    def res_key(s):
        try:
            return int(s.get("qualityLabel","0p").replace("p","").split("s")[0])
        except:
            return 0

    def fix_url(url):
        if url and url.startswith("/"):
            return instance_url + url
        return url

    # Try adaptive (1080p possible)
    video_streams = sorted(
        [f for f in adaptive_formats if f.get("type","").startswith("video/mp4") and f.get("url")],
        key=res_key, reverse=True
    )
    audio_streams = sorted(
        [f for f in adaptive_formats if f.get("type","").startswith("audio/") and f.get("url")],
        key=lambda s: int(s.get("bitrate",0)), reverse=True
    )

    print(f"\n  adaptive video streams: {len(video_streams)}")
    for s in video_streams[:5]:
        print(f"    {s.get('qualityLabel','?')} | {s.get('type','?')[:40]}")
    print(f"  audio streams: {len(audio_streams)}")

    # Pick best video matching quality priority
    best_video = None
    for q in QUALITY_PRIORITY:
        for s in video_streams:
            if q in s.get("qualityLabel",""):
                best_video = s
                break
        if best_video:
            break
    if not best_video and video_streams:
        best_video = video_streams[0]

    best_audio = audio_streams[0] if audio_streams else None

    if best_video and best_audio:
        best_video["url"] = fix_url(best_video["url"])
        best_audio["url"] = fix_url(best_audio["url"])
        print(f"  selected: {best_video.get('qualityLabel')} adaptive + audio")
        return "adaptive", best_video, best_audio

    # Fall back to combined formatStreams
    print(f"  no adaptive, trying combined streams...")
    combined = sorted(
        [f for f in format_streams if f.get("url")],
        key=res_key, reverse=True
    )
    print(f"  combined streams: {len(combined)}")
    for s in combined:
        print(f"    {s.get('qualityLabel','?')} | {s.get('type','?')[:40]}")

    if combined:
        best = combined[0]
        best["url"] = fix_url(best["url"])
        print(f"  selected: {best.get('qualityLabel')} combined")
        return "combined", best, None

    return None, None, None

def merge_video_audio(video_path, audio_path, output_path):
    """Merge video + audio with FFmpeg."""
    print(f"  merging with FFmpeg...")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-strict", "experimental",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg merge failed: {result.stderr[-200:]}")
    size = os.path.getsize(output_path) / (1024*1024)
    print(f"  merged! {size:.1f} MB")

def download_video(video_id, title):
    """Full download flow: info → best stream → download → merge if needed."""
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True)
    safe = "".join(c for c in title if c.isalnum() or c in " -_")[:50].strip()
    final = f"{DOWNLOADS_DIR}/{video_id}_{safe}.mp4"

    # Get info
    instance, data = get_video_info(video_id)
    if not data:
        raise Exception("All 15 Invidious instances failed — try again later")

    # Pick stream
    stream_type, vid_stream, aud_stream = pick_best_stream(data, instance)
    if not stream_type:
        raise Exception("No downloadable streams in Invidious response")

    if stream_type == "adaptive":
        vpath = f"{DOWNLOADS_DIR}/{video_id}_v.mp4"
        apath = f"{DOWNLOADS_DIR}/{video_id}_a.m4a"
        quality = vid_stream.get("qualityLabel","?")
        print(f"\n  downloading {quality} video stream...")
        if not download_file(vid_stream["url"], vpath, f"{quality} video"):
            raise Exception("Video stream download failed")
        print(f"  downloading audio stream...")
        if not download_file(aud_stream["url"], apath, "audio"):
            raise Exception("Audio stream download failed")
        merge_video_audio(vpath, apath, final)
        for f in [vpath, apath]:
            try: os.remove(f)
            except: pass
    else:
        quality = vid_stream.get("qualityLabel","?")
        print(f"\n  downloading {quality} combined stream...")
        if not download_file(vid_stream["url"], final, f"{quality} video"):
            raise Exception("Combined stream download failed")

    if not os.path.exists(final):
        raise Exception("Output file missing after download")

    size = os.path.getsize(final) / (1024*1024)
    if size < 1:
        raise Exception(f"Output file too small: {size:.1f}MB")

    return final

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Downloader (Invidious API, no browser)")
    print(f"{'='*60}\n")

    queue       = load_json(QUEUE_FILE, [])
    to_download = [v for v in queue if v.get("status") == "queued"]

    if not to_download:
        print("no videos in queue.")
        telegram("Downloader: No videos queued — skipping.")
        return

    print(f"{len(to_download)} video(s) to download")
    telegram(f"Download Started!\n{len(to_download)} video(s) via Invidious API (no browser needed)...")

    for v in to_download:
        vid_id = v["id"]
        title  = v["title"]
        mins   = v.get("duration_s", 0) // 60

        print(f"\n{'─'*50}")
        print(f"Downloading: {title[:70]}")
        print(f"Duration: {mins}m | Views: {v.get('views',0):,}")

        telegram(
            f"Downloading #{v.get('rank','?')}\n"
            f"{title[:60]}\n"
            f"{mins} min | {v.get('views',0):,} views\n"
            f"Fetching from Invidious..."
        )

        thumb_path = download_thumbnail(v.get("thumbnail_url",""), vid_id)

        try:
            video_path = download_video(vid_id, title)
            file_size  = os.path.getsize(video_path) / (1024*1024)

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
            telegram(f"Download FAILED\n{title[:50]}\nError: {err[:150]}")

        time.sleep(3)

    done   = sum(1 for v in queue if v.get("status") == "downloaded")
    failed = sum(1 for v in to_download if v.get("status") == "download_failed")

    print(f"\nDownload phase done: {done} success, {failed} failed")
    telegram(f"Download Phase Done!\nSuccess: {done} | Failed: {failed}\nNext: Watermark processing...")

if __name__ == "__main__":
    main()
