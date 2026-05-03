#!/usr/bin/env python3
"""
STEP 3: Add watermark to downloaded videos using FFmpeg
- Adds Max Lyrical Hub logo to TOP-RIGHT corner
- Medium size, semi-transparent
- Sends Telegram status updates
"""

import os
import json
import subprocess
import requests
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
QUEUE_FILE         = "state/download_queue.json"
WATERMARK_PATH     = "watermark/watermark.png"
PROCESSED_DIR      = "processed"

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

def add_watermark(input_path, output_path, watermark_path):
    """
    FFmpeg command to add watermark at top-right corner.
    Watermark is scaled to ~8% of video width, positioned 20px from edges.
    Semi-transparent (alpha 0.85).
    """
    # overlay=W-w-20:20 means: right edge minus watermark width minus 20px, 20px from top
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-i", watermark_path,
        "-filter_complex",
        # Scale watermark to 8% of video width, apply 85% opacity, position top-right
        "[1:v]scale=iw*8/100:-1,format=rgba,colorchannelmixer=aa=0.85[wm];"
        "[0:v][wm]overlay=W-w-20:20",
        "-codec:a", "copy",          # Keep audio untouched
        "-preset", "fast",           # Fast encoding
        "-crf", "18",                # High quality
        output_path
    ]
    print(f"  🎬 Running FFmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ FFmpeg error:\n{result.stderr[-500:]}")
        raise Exception(f"FFmpeg failed: {result.stderr[-200:]}")
    return True

def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Watermark Processor")
    print(f"{'='*60}\n")

    Path(PROCESSED_DIR).mkdir(exist_ok=True)
    queue = load_json(QUEUE_FILE, [])
    to_process = [v for v in queue if v.get("status") == "downloaded"]

    if not to_process:
        print("📭 No downloaded videos to process.")
        telegram("📭 <b>Watermark:</b> No videos to process.")
        return

    print(f"🎨 Processing {len(to_process)} video(s) with watermark...\n")
    telegram(f"🎨 <b>Watermark Processing Started!</b>\n🖼 Adding Max Lyrical Hub logo to {len(to_process)} video(s)...")

    for v in to_process:
        vid_id     = v["id"]
        title      = v["title"]
        video_path = v.get("video_path", "")

        if not video_path or not os.path.exists(video_path):
            print(f"  ❌ Video file not found: {video_path}")
            continue

        print(f"\n{'─'*50}")
        print(f"🎨 Processing: {title[:60]}")

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
        output_path = f"{PROCESSED_DIR}/{vid_id}_{safe_title}_watermarked.mp4"

        telegram(
            f"🎨 <b>Adding Watermark...</b>\n"
            f"📹 {title[:60]}\n"
            f"🖼 Placing logo at top-right corner..."
        )

        try:
            add_watermark(video_path, output_path, WATERMARK_PATH)

            file_size = os.path.getsize(output_path) / (1024*1024)
            print(f"  ✅ Watermarked: {output_path} ({file_size:.1f} MB)")

            # Update queue
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "processed"
                    item["processed_path"] = output_path
                    break

            save_json(QUEUE_FILE, queue)

            # Clean up original download to save space
            try:
                os.remove(video_path)
                print(f"  🗑️  Cleaned original download")
            except:
                pass

            telegram(
                f"✅ <b>Watermark Added!</b>\n"
                f"📹 {title[:60]}\n"
                f"💾 {file_size:.1f} MB\n"
                f"➡️ Next: Generating SEO with AI..."
            )

        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "process_failed"
                    item["error"] = str(e)
                    break
            save_json(QUEUE_FILE, queue)
            telegram(f"❌ <b>Watermark FAILED</b>\n📹 {title[:50]}\nError: {str(e)[:150]}")

    processed = sum(1 for v in queue if v.get("status") == "processed")
    print(f"\n✅ Watermark phase complete: {processed} videos ready")

if __name__ == "__main__":
    main()
