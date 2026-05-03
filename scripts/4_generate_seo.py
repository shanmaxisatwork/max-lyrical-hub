#!/usr/bin/env python3
"""
STEP 4: Generate SEO title, description, tags using OpenRouter AI
- Uses original video details as context
- Generates YouTube-optimized title, description with hashtags + search terms
- Free OpenRouter API key
"""

import os
import json
import requests
from pathlib import Path

TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
OPENROUTER_API_KEY  = os.environ["OPENROUTER_API_KEY"]
QUEUE_FILE          = "state/download_queue.json"

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

def generate_seo(original_title, original_description, original_tags, channel_name):
    """Call OpenRouter AI to generate SEO-optimized title + description."""

    tags_str = ", ".join(original_tags[:20]) if original_tags else "music, lyrics"
    # Truncate original description to avoid token overflow
    desc_preview = original_description[:500] if original_description else ""

    prompt = f"""You are a YouTube SEO expert. Based on this video's original details, generate optimized YouTube metadata for Max Lyrical Hub channel.

ORIGINAL VIDEO INFO:
- Title: {original_title}
- Channel: {channel_name}
- Tags: {tags_str}
- Description preview: {desc_preview}

TASK: Generate the following for Max Lyrical Hub's re-upload:

1. TITLE: Catchy, SEO-optimized YouTube title (max 100 chars). Keep the song/artist name. Add relevant keywords.

2. DESCRIPTION: Full YouTube description with:
   - Opening hook (2-3 sentences about the video)
   - Credits line: "Original by: {channel_name}"
   - Search terms section: "🔍 Search Terms:" followed by 15-20 relevant search keywords/phrases people would use to find this
   - Hashtag section: 20-30 relevant hashtags (mix of broad and niche music hashtags)
   - Standard footer: "Subscribe to Max Lyrical Hub for the best music! 🎵"

3. TAGS: 30-40 comma-separated YouTube tags (no # symbol, mix of short and long-tail keywords)

Respond ONLY in this exact JSON format, no markdown, no extra text:
{{"title": "...", "description": "...", "tags": ["tag1", "tag2", ...]}}"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/maxfindsstore/max-lyrical-hub",
        "X-Title": "Max Lyrical Hub Bot",
    }

    # Try free models in order
    models = [
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "openchat/openchat-7b:free",
    ]

    for model in models:
        print(f"  🤖 Trying model: {model}")
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.7,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Clean up possible markdown
            content = content.replace("```json", "").replace("```", "").strip()

            seo = json.loads(content)
            print(f"  ✅ SEO generated with {model}")
            return seo

        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error with {model}: {e}")
            print(f"  Raw response: {content[:200]}")
            continue
        except Exception as e:
            print(f"  ⚠️  {model} failed: {e}")
            continue

    # Fallback: generate basic SEO manually
    print("  ⚠️  All AI models failed, using fallback SEO")
    return {
        "title": f"{original_title[:90]} | Max Lyrical Hub",
        "description": (
            f"🎵 {original_title}\n\n"
            f"Original by: {channel_name}\n\n"
            f"🔍 Search Terms:\n{original_title} lyrics, {channel_name} songs, "
            f"new music {original_title}, {tags_str}\n\n"
            f"{'  '.join(['#' + t.replace(' ','') for t in (original_tags[:15] if original_tags else ['music', 'lyrics', 'newsong'])])}\n"
            f"#MaxLyricalHub #Music #Lyrics #NewSong #Trending\n\n"
            f"Subscribe to Max Lyrical Hub for the best music! 🎵"
        ),
        "tags": (original_tags[:30] if original_tags else []) + ["Max Lyrical Hub", "lyrics", "music", "new song", "trending"],
    }

def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — SEO Generator")
    print(f"{'='*60}\n")

    queue = load_json(QUEUE_FILE, [])
    to_generate = [v for v in queue if v.get("status") == "processed"]

    if not to_generate:
        print("📭 No processed videos to generate SEO for.")
        telegram("📭 <b>SEO Generator:</b> No videos to process.")
        return

    print(f"🤖 Generating SEO for {len(to_generate)} video(s)...\n")
    telegram(f"🤖 <b>AI SEO Generation Started!</b>\n📝 Generating titles, descriptions & tags for {len(to_generate)} video(s)...")

    for v in to_generate:
        vid_id       = v["id"]
        title        = v["title"]
        channel_name = v.get("channel_name", "Unknown Channel")

        print(f"\n{'─'*50}")
        print(f"🤖 Generating SEO for: {title[:60]}")

        telegram(
            f"🤖 <b>Generating SEO...</b>\n"
            f"📹 {title[:60]}\n"
            f"🔍 Creating optimized title, description & tags..."
        )

        try:
            seo = generate_seo(
                original_title=title,
                original_description=v.get("description_raw", ""),
                original_tags=v.get("tags", []),
                channel_name=channel_name,
            )

            generated_title = seo.get("title", title)
            generated_desc  = seo.get("description", "")
            generated_tags  = seo.get("tags", [])

            print(f"  📝 Title: {generated_title}")
            print(f"  📋 Description: {len(generated_desc)} chars")
            print(f"  🏷️  Tags: {len(generated_tags)} tags")

            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "seo_done"
                    item["seo_title"] = generated_title
                    item["seo_description"] = generated_desc
                    item["seo_tags"] = generated_tags[:500]  # YT max 500 chars in tags
                    break

            save_json(QUEUE_FILE, queue)

            telegram(
                f"✅ <b>SEO Generated!</b>\n"
                f"📝 Title: {generated_title[:60]}\n"
                f"🏷️ {len(generated_tags)} tags created\n"
                f"➡️ Ready for upload to Max Lyrical Hub!"
            )

        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "seo_failed"
                    item["error"] = str(e)
                    break
            save_json(QUEUE_FILE, queue)
            telegram(f"❌ <b>SEO FAILED</b>\n📹 {title[:50]}\n{str(e)[:150]}")

    seo_done = sum(1 for v in queue if v.get("status") == "seo_done")
    print(f"\n✅ SEO phase complete: {seo_done} videos ready for upload")

if __name__ == "__main__":
    main()
