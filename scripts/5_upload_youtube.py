#!/usr/bin/env python3
"""
STEP 5: Upload processed videos to Max Lyrical Hub YouTube channel
- Uses YouTube Data API v3 with OAuth2
- Sets custom thumbnail (extracted from original video)
- Schedules uploads at optimal times
- Sends Telegram alert on completion with YT link
"""

import os
import json
import time
import datetime
import requests
import tempfile
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
QUEUE_FILE         = "state/download_queue.json"

# Upload schedule (IST times converted to UTC: IST = UTC+5:30)
# 3PM IST = 09:30 UTC | 5PM IST = 11:30 UTC | 7PM IST = 13:30 UTC | 9PM IST = 15:30 UTC | 11PM IST = 17:30 UTC
UPLOAD_SCHEDULE_UTC = [
    "09:30",  # 3:00 PM IST
    "11:30",  # 5:00 PM IST
    "13:30",  # 7:00 PM IST
    "15:30",  # 9:00 PM IST
    "17:30",  # 11:00 PM IST
]

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

def get_youtube_service():
    """Build authenticated YouTube service using stored OAuth credentials."""
    oauth_json = os.environ.get("YT_OAUTH_JSON", "")
    if not oauth_json:
        raise Exception("YT_OAUTH_JSON secret not set!")

    creds_data = json.loads(oauth_json)

    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube"],
    )

    # Auto-refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        print("  🔄 OAuth token refreshed")

    return build("youtube", "v3", credentials=creds)

def get_scheduled_time(index):
    """Get the scheduled publish time for a given video index (0-4)."""
    now_utc = datetime.datetime.utcnow()
    today   = now_utc.date()

    if index < len(UPLOAD_SCHEDULE_UTC):
        time_str = UPLOAD_SCHEDULE_UTC[index]
        h, m = map(int, time_str.split(":"))
        scheduled = datetime.datetime(today.year, today.month, today.day, h, m, 0)

        # If time already passed today, schedule for tomorrow
        if scheduled <= now_utc:
            scheduled += datetime.timedelta(days=1)
    else:
        # Extra videos: add 2h gaps after last slot
        base_h, base_m = map(int, UPLOAD_SCHEDULE_UTC[-1].split(":"))
        base = datetime.datetime(today.year, today.month, today.day, base_h, base_m, 0)
        if base <= now_utc:
            base += datetime.timedelta(days=1)
        scheduled = base + datetime.timedelta(hours=2 * (index - len(UPLOAD_SCHEDULE_UTC) + 1))

    return scheduled.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def upload_video(youtube, video_path, title, description, tags, category_id, schedule_time):
    """Upload video to YouTube and return video ID."""
    tags_limited = tags[:500] if isinstance(tags, list) else []

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags_limited,
            "categoryId": category_id or "10",  # 10 = Music
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",   # Start private, will be scheduled
            "publishAt": schedule_time,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=50 * 1024 * 1024,  # 50MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    print(f"  📤 Uploading (this may take several minutes)...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct % 20 == 0:  # Log every 20%
                print(f"     Upload progress: {pct}%")

    return response.get("id")

def set_thumbnail(youtube, video_id, thumbnail_path):
    """Set custom thumbnail for the uploaded video."""
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print(f"  ⚠️  No thumbnail file found, skipping")
        return False

    media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media
        ).execute()
        print(f"  🖼️  Thumbnail set successfully")
        return True
    except Exception as e:
        print(f"  ⚠️  Thumbnail upload failed: {e}")
        return False

def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — YouTube Uploader")
    print(f"{'='*60}\n")

    queue = load_json(QUEUE_FILE, [])
    to_upload = [v for v in queue if v.get("status") == "seo_done"]

    if not to_upload:
        print("📭 No videos ready for upload.")
        telegram("📭 <b>Uploader:</b> No videos ready to upload yet.")
        return

    print(f"📤 {len(to_upload)} video(s) to upload\n")
    telegram(f"📤 <b>Upload Phase Started!</b>\n🚀 Uploading {len(to_upload)} video(s) to Max Lyrical Hub...")

    try:
        youtube = get_youtube_service()
        print("  ✅ YouTube OAuth authenticated\n")
    except Exception as e:
        msg = f"❌ YouTube Auth FAILED: {e}"
        print(msg)
        telegram(f"❌ <b>Upload Auth FAILED</b>\n{str(e)[:200]}\nCheck YT_OAUTH_JSON secret!")
        return

    upload_index = 0
    for v in to_upload:
        vid_id       = v["id"]
        title        = v.get("seo_title", v["title"])
        description  = v.get("seo_description", "")
        tags         = v.get("seo_tags", [])
        video_path   = v.get("processed_path", "")
        thumb_path   = v.get("thumbnail_path", "")
        category_id  = v.get("category_id", "10")
        schedule_time = get_scheduled_time(upload_index)

        # Convert UTC schedule back to IST for display
        sched_dt = datetime.datetime.strptime(schedule_time, "%Y-%m-%dT%H:%M:%S.000Z")
        sched_ist = sched_dt + datetime.timedelta(hours=5, minutes=30)
        sched_ist_str = sched_ist.strftime("%d %b %Y, %I:%M %p IST")

        print(f"\n{'─'*50}")
        print(f"📤 Uploading: {title[:60]}")
        print(f"   Scheduled: {sched_ist_str}")

        if not video_path or not os.path.exists(video_path):
            print(f"  ❌ Video file missing: {video_path}")
            telegram(f"❌ <b>Upload FAILED</b>\n📹 {title[:50]}\nVideo file not found!")
            continue

        telegram(
            f"📤 <b>Uploading to YouTube...</b>\n"
            f"📹 {title[:60]}\n"
            f"⏰ Scheduled: {sched_ist_str}\n"
            f"⏳ This may take a few minutes..."
        )

        try:
            yt_video_id = upload_video(
                youtube, video_path, title, description, tags, category_id, schedule_time
            )

            print(f"  ✅ Uploaded! Video ID: {yt_video_id}")

            # Set thumbnail
            thumb_success = set_thumbnail(youtube, yt_video_id, thumb_path)

            yt_link = f"https://www.youtube.com/watch?v={yt_video_id}"

            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "uploaded"
                    item["yt_video_id"] = yt_video_id
                    item["yt_link"] = yt_link
                    item["scheduled_at"] = sched_ist_str
                    break

            save_json(QUEUE_FILE, queue)

            # Clean up processed video to save GitHub Actions storage
            try:
                os.remove(video_path)
                if thumb_path and os.path.exists(thumb_path):
                    os.remove(thumb_path)
                print(f"  🗑️  Cleaned up local files")
            except:
                pass

            telegram(
                f"🎉 <b>UPLOAD COMPLETE!</b>\n\n"
                f"📹 <b>{title[:60]}</b>\n"
                f"📺 Channel: Max Lyrical Hub\n"
                f"⏰ Goes live: {sched_ist_str}\n"
                f"🖼️ Thumbnail: {'✅ Set' if thumb_success else '⚠️ Default'}\n\n"
                f"🔗 {yt_link}"
            )

            print(f"  🎉 Done! {yt_link}")
            upload_index += 1
            time.sleep(5)  # Brief pause between uploads

        except Exception as e:
            print(f"  ❌ UPLOAD FAILED: {e}")
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "upload_failed"
                    item["error"] = str(e)
                    break
            save_json(QUEUE_FILE, queue)
            telegram(
                f"❌ <b>Upload FAILED</b>\n"
                f"📹 {title[:50]}\n"
                f"Error: {str(e)[:200]}"
            )

    uploaded = sum(1 for v in queue if v.get("status") == "uploaded")
    failed   = sum(1 for v in to_upload if v.get("status") == "upload_failed")

    summary = (
        f"📊 <b>Upload Session Complete!</b>\n"
        f"✅ Uploaded: {uploaded}\n"
        f"❌ Failed: {failed}\n"
        f"🎵 Max Lyrical Hub is growing! 🚀"
    )
    print(f"\n{summary.replace('<b>', '').replace('</b>', '')}")
    telegram(summary)

if __name__ == "__main__":
    main()
