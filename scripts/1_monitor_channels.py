#!/usr/bin/env python3
"""
STEP 1: Monitor source channels for new long videos
- Resolves @handles to UC IDs automatically
- Detects new uploads (long videos only, no shorts)
- Ranks by engagement score (views + likes + comments)
- Picks TOP 5 videos
- Sends Telegram alert with findings
"""

import os
import json
import requests
import datetime
import time
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────────
CHANNEL_HANDLES = [
    "@UBII2B",
    "@7clouds",
    "@VibeBirdPrime",
    "@VibeBird",
    "@VdjShyamyt",
    "@varipettiii",
    "@seventyskye",
    "@D-MuzeIndia",
    "@WaVerNoir_26",
    "@creativchaos",
    "@Illuvibess",
]

YT_API_KEYS = [
    os.environ["YT_API_KEY_1"],
    os.environ["YT_API_KEY_2"],
    os.environ["YT_API_KEY_3"],
    os.environ["YT_API_KEY_4"],
]

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE      = "state/seen_videos.json"
QUEUE_FILE      = "state/download_queue.json"
TOP_N_VIDEOS    = 5
MIN_DURATION_S  = 61   # anything above 60s = long video

# ─── API KEY ROTATION ─────────────────────────────────────────────────────────
_key_index = 0

def get_key():
    global _key_index
    key = YT_API_KEYS[_key_index % len(YT_API_KEYS)]
    return key

def rotate_key():
    global _key_index
    _key_index += 1
    print(f"  [KEY] Rotated to key #{_key_index % len(YT_API_KEYS) + 1}")

def yt_get(url, params, retries=4):
    """YouTube API GET with automatic key rotation on quota errors."""
    for attempt in range(retries):
        params["key"] = get_key()
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 403:
                data = r.json()
                reason = data.get("error", {}).get("errors", [{}])[0].get("reason", "")
                if reason in ("quotaExceeded", "dailyLimitExceeded"):
                    print(f"  [QUOTA] Key exhausted, rotating...")
                    rotate_key()
                    time.sleep(1)
                    continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"  [ERROR] API request failed: {e}")
            rotate_key()
            time.sleep(2)
    return None

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
def telegram(msg):
    """Send Telegram message — plain text only, no HTML, safe for any language/chars."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Strip HTML tags to prevent parse errors with special chars in video titles
    clean = msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": clean,
        }, timeout=10)
    except Exception as e:
        print(f"  [TELEGRAM ERROR] {e}")

# ─── HELPERS ──────────────────────────────────────────────────────────────────
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

def iso8601_duration_to_seconds(duration):
    """Convert PT1H2M3S → seconds"""
    import re
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s

def is_short(title, description, duration_s):
    """Filter out Shorts by duration and keywords."""
    if duration_s <= 60:
        return True
    keywords = ["#shorts", "#short", "#ytshorts", "#youtubeshorts"]
    combined = (title + " " + description).lower()
    if any(k in combined for k in keywords):
        return True
    return False

# ─── RESOLVE HANDLES → UC IDs ─────────────────────────────────────────────────
def resolve_handle_to_ucid(handle):
    """Resolve @handle to channel UC ID using YouTube API."""
    handle_clean = handle.lstrip("@")
    data = yt_get(
        "https://www.googleapis.com/youtube/v3/channels",
        {"part": "id,snippet", "forHandle": handle_clean, "maxResults": 1}
    )
    if data and data.get("items"):
        item = data["items"][0]
        return item["id"], item["snippet"]["title"]
    print(f"  [WARN] Could not resolve handle: {handle}")
    return None, None

# ─── FETCH CHANNEL VIDEOS ─────────────────────────────────────────────────────
def get_recent_videos(channel_id, channel_name, hours_back=24):
    """Get videos uploaded in the last N hours from a channel."""
    published_after = (
        datetime.datetime.utcnow() - datetime.timedelta(hours=hours_back)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Get uploads playlist ID
    data = yt_get(
        "https://www.googleapis.com/youtube/v3/channels",
        {"part": "contentDetails", "id": channel_id}
    )
    if not data or not data.get("items"):
        return []

    uploads_playlist = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Get recent videos from playlist
    videos = []
    page_token = None
    while True:
        params = {
            "part": "snippet",
            "playlistId": uploads_playlist,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        playlist_data = yt_get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params
        )
        if not playlist_data:
            break

        for item in playlist_data.get("items", []):
            published = item["snippet"]["publishedAt"]
            if published >= published_after:
                vid_id = item["snippet"]["resourceId"]["videoId"]
                videos.append({
                    "id": vid_id,
                    "channel_name": channel_name,
                    "channel_id": channel_id,
                    "title": item["snippet"]["title"],
                    "published": published,
                    "thumbnail": item["snippet"].get("thumbnails", {}).get("maxres", 
                                 item["snippet"].get("thumbnails", {}).get("high", {})).get("url", ""),
                })
            else:
                # Playlist is newest-first, so stop once we go past our window
                return videos

        page_token = playlist_data.get("nextPageToken")
        if not page_token:
            break

    return videos

# ─── GET VIDEO STATS + DETAILS ─────────────────────────────────────────────────
def enrich_videos(video_ids):
    """Fetch stats + duration for a batch of video IDs."""
    enriched = {}
    # Batch in groups of 50
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        data = yt_get(
            "https://www.googleapis.com/youtube/v3/videos",
            {
                "part": "statistics,contentDetails,snippet",
                "id": ",".join(batch),
            }
        )
        if not data:
            continue
        for item in data.get("items", []):
            vid_id = item["id"]
            stats  = item.get("statistics", {})
            detail = item.get("contentDetails", {})
            snippet = item.get("snippet", {})
            duration_s = iso8601_duration_to_seconds(detail.get("duration", "PT0S"))
            views    = int(stats.get("viewCount", 0))
            likes    = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            # Engagement score: weighted
            engagement = views + (likes * 5) + (comments * 10)
            enriched[vid_id] = {
                "duration_s": duration_s,
                "views": views,
                "likes": likes,
                "comments": comments,
                "engagement": engagement,
                "description": snippet.get("description", ""),
                "tags": snippet.get("tags", []),
                "category_id": snippet.get("categoryId", "10"),
                # Best thumbnail
                "thumbnail_url": (
                    snippet.get("thumbnails", {}).get("maxres", 
                    snippet.get("thumbnails", {}).get("standard",
                    snippet.get("thumbnails", {}).get("high", {}))).get("url", "")
                ),
            }
    return enriched

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Channel Monitor")
    print(f"Run time: {now_str}")
    print(f"{'='*60}\n")

    telegram(f"🔍 <b>Max Lyrical Hub Bot Started</b>\n⏰ {now_str}\nScanning {len(CHANNEL_HANDLES)} channels for new videos...")

    # Load seen videos state — force dict type (corrupt cache can load as list)
    seen = load_json(STATE_FILE, {})
    if not isinstance(seen, dict):
        print("  [WARN] seen_videos.json corrupted, resetting to empty dict")
        seen = {}

    # Load existing queue — force list type
    existing_queue = load_json(QUEUE_FILE, [])
    if not isinstance(existing_queue, list):
        print("  [WARN] download_queue.json corrupted, resetting to empty list")
        existing_queue = []

    queued_ids = {v["id"] for v in existing_queue if isinstance(v, dict) and "id" in v}

    all_new_videos = []

    # Step 1: Resolve handles → UC IDs
    print("📡 Resolving channel handles...\n")
    channels = []
    for handle in CHANNEL_HANDLES:
        uc_id, name = resolve_handle_to_ucid(handle)
        if uc_id:
            channels.append({"handle": handle, "id": uc_id, "name": name})
            print(f"  ✅ {handle} → {uc_id} ({name})")
        else:
            print(f"  ❌ {handle} → Could not resolve")
        time.sleep(0.3)

    # Save resolved channels for reference
    save_json("state/channels.json", channels)

    print(f"\n📺 Fetching recent videos from {len(channels)} channels...\n")

    # Step 2: Fetch recent videos
    for ch in channels:
        print(f"  Checking: {ch['name']} ({ch['handle']})")
        videos = get_recent_videos(ch["id"], ch["name"], hours_back=24)
        print(f"    Found {len(videos)} video(s) in last 24h")
        for v in videos:
            if v["id"] not in seen and v["id"] not in queued_ids:
                all_new_videos.append(v)
        time.sleep(0.5)

    if not all_new_videos:
        msg = "😴 <b>No new videos found</b> in the last 24 hours across all channels.\nBot will check again tomorrow morning."
        print("\n" + msg.replace("<b>", "").replace("</b>", ""))
        telegram(msg)
        return

    print(f"\n🎬 Found {len(all_new_videos)} new video(s) total. Fetching stats...\n")

    # Step 3: Enrich with stats
    vid_ids = [v["id"] for v in all_new_videos]
    enriched = enrich_videos(vid_ids)

    # Step 4: Filter long videos only, attach stats
    long_videos = []
    for v in all_new_videos:
        info = enriched.get(v["id"], {})
        duration_s = info.get("duration_s", 0)
        title = v["title"]
        desc  = info.get("description", "")

        if is_short(title, desc, duration_s):
            print(f"  ⏭️  SKIP (Short/Reel): {title[:50]}")
            seen[v["id"]] = "skipped_short"
            continue

        v.update(info)
        long_videos.append(v)
        mins = duration_s // 60
        secs = duration_s % 60
        print(f"  ✅ LONG VIDEO [{mins}m{secs}s] | 👁 {info.get('views',0):,} | 👍 {info.get('likes',0):,} | 💬 {info.get('comments',0):,} | Score: {info.get('engagement',0):,}")
        print(f"     {title[:70]}")

    if not long_videos:
        msg = "📭 <b>All new videos were Shorts</b> — no long videos found today.\nBot will check again tomorrow."
        telegram(msg)
        save_json(STATE_FILE, seen)
        return

    # Step 5: Rank by engagement, pick TOP 5
    long_videos.sort(key=lambda x: x.get("engagement", 0), reverse=True)
    top_videos = long_videos[:TOP_N_VIDEOS]

    print(f"\n🏆 TOP {len(top_videos)} VIDEOS BY ENGAGEMENT:\n")
    queue_to_add = []
    for rank, v in enumerate(top_videos, 1):
        mins = v.get("duration_s", 0) // 60
        secs = v.get("duration_s", 0) % 60
        print(f"  #{rank} [{mins}m{secs}s] {v['title'][:60]}")
        print(f"       👁 {v.get('views',0):,} | 👍 {v.get('likes',0):,} | 💬 {v.get('comments',0):,} | Score: {v.get('engagement',0):,}")
        print(f"       🔗 https://youtube.com/watch?v={v['id']}\n")

        queue_to_add.append({
            "id": v["id"],
            "title": v["title"],
            "channel_name": v["channel_name"],
            "url": f"https://www.youtube.com/watch?v={v['id']}",
            "duration_s": v.get("duration_s", 0),
            "views": v.get("views", 0),
            "likes": v.get("likes", 0),
            "comments": v.get("comments", 0),
            "engagement": v.get("engagement", 0),
            "thumbnail_url": v.get("thumbnail_url", ""),
            "tags": v.get("tags", []),
            "category_id": v.get("category_id", "10"),
            "description_raw": v.get("description", ""),
            "rank": rank,
            "status": "queued",
            "queued_at": now_str,
        })
        # Mark as seen so we don't re-queue
        seen[v["id"]] = "queued"

    # Also mark other new (non-top) videos as seen so we skip them next time
    for v in long_videos[TOP_N_VIDEOS:]:
        seen[v["id"]] = "skipped_not_top5"

    # Append to queue
    updated_queue = existing_queue + queue_to_add
    save_json(QUEUE_FILE, updated_queue)
    save_json(STATE_FILE, seen)

    # Telegram summary — use plain text mode to avoid HTML parse errors
    # (video titles can contain Malayalam, special chars that break HTML mode)
    def safe(text):
        """Strip any chars that could break Telegram messages."""
        return str(text).replace("<", "").replace(">", "").replace("&", "and")

    lines = [f"✅ Monitor Complete!\n📊 Found {len(top_videos)} long videos queued:\n"]
    for v in queue_to_add:
        mins = v["duration_s"] // 60
        lines.append(
            f"#{v['rank']} — {safe(v['title'][:50])}\n"
            f"   📺 {safe(v['channel_name'])} | ⏱ {mins}m | 👁 {v['views']:,}\n"
            f"   🔗 https://youtube.com/watch?v={v['id']}\n"
        )
    lines.append("⬇️ Download + Processing starts in afternoon run!")

    # Send without parse_mode to avoid HTML errors
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "\n".join(lines),
        }, timeout=10)
    except Exception as e:
        print(f"  [TELEGRAM ERROR] {e}")

    print(f"\n✅ {len(queue_to_add)} videos added to queue. Done!\n")

if __name__ == "__main__":
    main()
