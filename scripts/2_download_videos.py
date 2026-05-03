#!/usr/bin/env python3
"""
STEP 2: Download videos using Playwright on yt5s.biz
- Opens real Chromium browser (headless)
- Navigates yt5s.biz like a human
- Handles Cloudflare delay
- Selects best quality (1080p or highest available)
- Downloads video file
- Sends Telegram status at each stage
"""

import os
import json
import time
import shutil
import asyncio
import requests
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
QUEUE_FILE         = "state/download_queue.json"
DOWNLOADS_DIR      = "downloads"
SITE_URL           = "https://yt5s.biz"

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def telegram(msg):
    """Send plain text Telegram message - safe for Malayalam/special chars."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    clean = msg.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","")
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": clean,
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
    """Download the original video's thumbnail."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            thumb_path = f"{DOWNLOADS_DIR}/{video_id}_thumbnail.jpg"
            with open(thumb_path, "wb") as f:
                f.write(r.content)
            print(f"  ✅ Thumbnail downloaded: {thumb_path}")
            return thumb_path
    except Exception as e:
        print(f"  [WARN] Thumbnail download failed: {e}")
    return None

# ─── PLAYWRIGHT DOWNLOADER ────────────────────────────────────────────────────
async def download_video_playwright(yt_url, video_id, title):
    """
    Opens yt5s.biz in headless Chromium, pastes URL,
    waits for processing, clicks best quality download button.
    """
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True)
    output_path = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )

        page = await context.new_page()

        # Remove webdriver detection
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        try:
            print(f"  🌐 Opening {SITE_URL}...")
            await page.goto(SITE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # ── Step 1: Find the URL input and paste YouTube link ──
            print(f"  📋 Pasting URL: {yt_url}")

            # Try multiple possible input selectors
            input_selectors = [
                "input[name='query']",
                "input[type='text']",
                "input[placeholder*='youtube']",
                "input[placeholder*='YouTube']",
                "input[placeholder*='link']",
                "input[placeholder*='URL']",
                "#query",
                ".search-input",
            ]

            input_el = None
            for sel in input_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        input_el = el
                        print(f"    Found input with selector: {sel}")
                        break
                except:
                    continue

            if not input_el:
                # Fallback: find any visible text input
                inputs = await page.query_selector_all("input")
                for inp in inputs:
                    if await inp.is_visible():
                        input_type = await inp.get_attribute("type") or "text"
                        if input_type in ("text", "url", "search", ""):
                            input_el = page.locator(f"input >> nth={inputs.index(inp)}")
                            print(f"    Found input via fallback scan")
                            break

            if not input_el:
                raise Exception("Could not find URL input field on page")

            await input_el.click()
            await input_el.fill("")
            await page.wait_for_timeout(500)
            await input_el.type(yt_url, delay=50)  # Type like a human
            await page.wait_for_timeout(500)

            # ── Step 2: Click the Download/Search button ──
            print(f"  🖱️  Clicking download button...")
            btn_selectors = [
                "button[type='submit']",
                "button.btn-success",
                "button.btn-primary",
                "input[type='submit']",
                "button:has-text('Download')",
                "button:has-text('Start')",
                "button:has-text('Convert')",
                "button:has-text('Go')",
                "#btn-submit",
                ".btn-download",
            ]

            clicked = False
            for sel in btn_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        clicked = True
                        print(f"    Clicked button: {sel}")
                        break
                except:
                    continue

            if not clicked:
                # Try pressing Enter on the input
                await input_el.press("Enter")
                print(f"    Pressed Enter as fallback")

            # ── Step 3: Wait for Cloudflare check + processing (18-25 seconds) ──
            print(f"  ⏳ Waiting for Cloudflare check + processing (25 seconds)...")
            await page.wait_for_timeout(25000)

            # Wait for download buttons to appear
            # Look for quality buttons - specifically 1080p or best available
            print(f"  🔍 Looking for quality/download buttons...")
            await page.wait_for_timeout(3000)

            # ── Step 4: Select best quality download button ──
            # The button has class "btn-success" and data-fquality attribute
            # We want the highest quality: prefer 1080p, fallback to best available

            best_btn = None
            best_quality = 0
            quality_priority = ["2160", "1440", "1080", "720", "480", "360"]

            # Try to find quality buttons by data-fquality attribute
            for quality in quality_priority:
                try:
                    btn = page.locator(f"button[data-fquality='{quality}'][data-ftype='mp4']").first
                    if await btn.is_visible(timeout=2000):
                        best_btn = btn
                        print(f"    Found quality button: {quality}p MP4")
                        break
                except:
                    continue

            # Fallback: find all btn-success buttons and pick by quality text
            if not best_btn:
                print(f"    Trying fallback button search...")
                all_btns = await page.query_selector_all("button.btn-success, button.btn-primary, a.btn-success")
                for b in all_btns:
                    text = (await b.inner_text()).strip().lower()
                    parent_text = ""
                    try:
                        parent = await b.evaluate_handle("el => el.closest('tr') || el.closest('div')")
                        parent_text = await page.evaluate("el => el ? el.innerText : ''", parent)
                    except:
                        pass
                    combined = (text + " " + parent_text).lower()
                    for q in ["2160", "1440", "1080", "720", "480", "360"]:
                        if q in combined and int(q) > best_quality:
                            best_quality = int(q)
                            best_btn = b
                            print(f"    Found quality {q}p via text search")
                            break

            # Absolute last resort: click 3rd download button (as per your original steps)
            if not best_btn:
                print(f"    Clicking 3rd option as last resort...")
                all_btns = await page.query_selector_all("button.btn-success")
                if len(all_btns) >= 3:
                    best_btn = all_btns[2]  # 3rd button = 1080p per your observation
                elif len(all_btns) > 0:
                    best_btn = all_btns[0]

            if not best_btn:
                raise Exception("No download quality buttons found")

            # ── Step 5: Click best quality button and handle download popup ──
            print(f"  📥 Clicking download button...")

            # Set up download listener BEFORE clicking
            async with page.expect_download(timeout=60000) as download_info:
                await best_btn.click()
                await page.wait_for_timeout(2000)

                # Handle possible "Download NOW" popup
                popup_selectors = [
                    "button:has-text('Download NOW')",
                    "button:has-text('Download Now')",
                    "a:has-text('Download NOW')",
                    "a:has-text('Download Now')",
                    ".btn-success:has-text('Download')",
                ]
                for sel in popup_selectors:
                    try:
                        popup_btn = page.locator(sel).first
                        if await popup_btn.is_visible(timeout=3000):
                            print(f"    Clicking popup: {sel}")
                            await popup_btn.click()
                            break
                    except:
                        continue

                download = await download_info.value

            # ── Step 6: Save the file ──
            safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
            output_path = f"{DOWNLOADS_DIR}/{video_id}_{safe_title}.mp4"
            await download.save_as(output_path)
            print(f"  ✅ Downloaded to: {output_path}")
            file_size = os.path.getsize(output_path) / (1024*1024)
            print(f"     Size: {file_size:.1f} MB")

        except PlaywrightTimeout as e:
            print(f"  ❌ Playwright timeout: {e}")
            # Take screenshot for debugging
            try:
                await page.screenshot(path=f"{DOWNLOADS_DIR}/error_{video_id}.png")
                print(f"  📸 Screenshot saved for debugging")
            except:
                pass
            raise

        except Exception as e:
            print(f"  ❌ Download error: {e}")
            try:
                await page.screenshot(path=f"{DOWNLOADS_DIR}/error_{video_id}.png")
            except:
                pass
            raise

        finally:
            await browser.close()

    return output_path

# ─── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Video Downloader")
    print(f"{'='*60}\n")

    queue = load_json(QUEUE_FILE, [])
    to_download = [v for v in queue if v.get("status") == "queued"]

    if not to_download:
        print("📭 No videos in queue to download.")
        telegram("📭 <b>Downloader:</b> No videos in queue — skipping.")
        return

    print(f"📋 {len(to_download)} video(s) to download\n")
    telegram(f"⬇️ <b>Download Started!</b>\n📋 {len(to_download)} video(s) to process...")

    for v in to_download:
        vid_id    = v["id"]
        yt_url    = v["url"]
        title     = v["title"]
        mins      = v.get("duration_s", 0) // 60

        print(f"\n{'─'*50}")
        print(f"📥 Downloading: {title[:60]}")
        print(f"   Duration: {mins}m | 👁 {v.get('views',0):,}")
        print(f"   URL: {yt_url}")

        telegram(
            f"⬇️ <b>Downloading #{v.get('rank', '?')}</b>\n"
            f"📹 {title[:60]}\n"
            f"⏱ {mins} min | 👁 {v.get('views',0):,} views\n"
            f"🌐 Starting Playwright browser..."
        )

        # Download thumbnail first (fast, direct URL)
        thumb_path = download_thumbnail(v.get("thumbnail_url", ""), vid_id)

        # Download video via Playwright
        try:
            video_path = await download_video_playwright(yt_url, vid_id, title)

            # Update queue status
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "downloaded"
                    item["video_path"] = video_path
                    item["thumbnail_path"] = thumb_path
                    break

            save_json(QUEUE_FILE, queue)

            file_size = os.path.getsize(video_path) / (1024*1024)
            telegram(
                f"✅ <b>Download Complete!</b>\n"
                f"📹 {title[:60]}\n"
                f"💾 File size: {file_size:.1f} MB\n"
                f"🖼 Thumbnail: {'✅ Saved' if thumb_path else '❌ Not found'}\n"
                f"➡️ Next: Adding watermark..."
            )
            print(f"  ✅ SUCCESS! {file_size:.1f} MB")

        except Exception as e:
            error_msg = str(e)[:200]
            print(f"  ❌ FAILED: {error_msg}")

            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "download_failed"
                    item["error"] = error_msg
                    break

            save_json(QUEUE_FILE, queue)
            telegram(
                f"❌ <b>Download FAILED</b>\n"
                f"📹 {title[:50]}\n"
                f"Error: {error_msg[:150]}\n"
                f"⏭ Skipping to next video..."
            )

        # Small delay between downloads
        await asyncio.sleep(5)

    downloaded = sum(1 for v in queue if v.get("status") == "downloaded")
    failed     = sum(1 for v in to_download if v.get("status") == "download_failed")
    print(f"\n✅ Download phase complete: {downloaded} done, {failed} failed")

if __name__ == "__main__":
    asyncio.run(main())
