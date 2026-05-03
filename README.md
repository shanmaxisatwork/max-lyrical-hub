# 🎵 Max Lyrical Hub — YouTube Automation Bot

Fully automated system that monitors source YouTube channels, downloads top videos, adds watermark, generates AI SEO, and uploads to **Max Lyrical Hub** — all running free on GitHub Actions.

---

## 🔄 How It Works

```
7:00 AM IST — GitHub Actions wakes up
├── Scans 11 source channels for new videos (last 24h)
├── Filters: Long videos only (no Shorts)
├── Ranks by engagement (views + likes + comments)
├── Picks TOP 5 videos
└── 📱 Telegram: "Found X videos, queued for afternoon"

2:30 PM IST — GitHub Actions wakes up
├── ⬇️  Downloads via Playwright on yt5s.biz (best quality)
│       📱 Telegram: "Downloading video X..."
├── 🎨  Adds watermark (Max Lyrical Hub logo, top-right)
│       📱 Telegram: "Watermark added!"
├── 🤖  AI generates Title + Description + SEO + Hashtags
│       📱 Telegram: "SEO generated!"
└── 📤  Uploads to Max Lyrical Hub (scheduled at peak times)
        📱 Telegram: "✅ UPLOADED! [link] — goes live at 5PM"
```

**Upload Schedule (IST):** 3PM → 5PM → 7PM → 9PM → 11PM

---

## 📋 Source Channels Monitored

| Handle | Channel |
|--------|---------|
| @UBII2B | UBII2B |
| @7clouds | 7 Clouds |
| @VibeBirdPrime | VibeBird Prime |
| @VibeBird | VibeBird |
| @VdjShyamyt | VDJ Shyam |
| @varipettiii | varipettiii |
| @seventyskye | Seventy Skye |
| @D-MuzeIndia | D-Muze India |
| @WaVerNoir_26 | WaVerNoir |
| @creativchaos | Creativ Chaos |
| @Illuvibess | Illuvibess |

---

## 🔐 GitHub Secrets Required

Go to: **Your Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | What It Is | Where to Get |
|-------------|-----------|--------------|
| `YT_API_KEY_1` | YouTube Data API v3 Key | [Google Cloud Console](https://console.cloud.google.com) |
| `YT_API_KEY_2` | YouTube Data API v3 Key (2nd) | Same as above |
| `YT_API_KEY_3` | YouTube Data API v3 Key (3rd) | Same as above |
| `YT_API_KEY_4` | YouTube Data API v3 Key (4th) | Same as above |
| `YT_OAUTH_JSON` | OAuth credentials JSON | Run `python setup_oauth.py` |
| `OPENROUTER_API_KEY` | OpenRouter AI free key | [openrouter.ai](https://openrouter.ai) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | [@userinfobot](https://t.me/userinfobot) on Telegram |

---

## 🚀 First-Time Setup (Step by Step)

### Step 1: Fork/Create this repo on GitHub
```bash
# On your laptop (or GitHub UI):
# Create new repo at: github.com/maxfindsstore
# Upload all these files
```

### Step 2: Get 4 YouTube API Keys
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Go to Credentials → Create API Key → Copy it
4. Repeat 3 more times (or create 4 separate projects for safety)

### Step 3: Generate OAuth Credentials
Run this **on your laptop** (one time only):
```bash
pip install google-auth-oauthlib google-api-python-client
python setup_oauth.py
```
- It opens a browser
- Log in with `generalpurposeemailforuses@gmail.com`
- Copy the JSON output → Add as `YT_OAUTH_JSON` secret

### Step 4: Set Up Telegram Bot
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Get your `bot_token`
3. Message [@userinfobot](https://t.me/userinfobot) → Get your `chat_id`
4. Add both as secrets

### Step 5: Get OpenRouter Key
1. Sign up at [openrouter.ai](https://openrouter.ai)
2. Go to Keys → Create new key (free)
3. Add as `OPENROUTER_API_KEY` secret

### Step 6: Add Secrets to GitHub
Go to your repo → Settings → Secrets → Add all 8 secrets above

### Step 7: Enable GitHub Actions
- Go to Actions tab → Enable workflows
- The bot will automatically run at 7AM and 2:30PM IST every day!

### Step 8: Test manually
- Go to Actions → "Max Lyrical Hub Automation" → "Run workflow"
- Select `monitor_only` first to test channel scanning

---

## 📱 Telegram Notifications You'll Receive

| Time | Message |
|------|---------|
| 7:00 AM | "🔍 Scanning 11 channels..." |
| 7:05 AM | "✅ Found 5 videos queued!" |
| 2:30 PM | "⬇️ Downloading Video #1..." |
| 2:35 PM | "✅ Download Complete! 245 MB" |
| 2:36 PM | "🎨 Adding Watermark..." |
| 2:37 PM | "✅ Watermark Added!" |
| 2:38 PM | "🤖 Generating SEO..." |
| 2:39 PM | "✅ SEO Generated!" |
| 2:40 PM | "📤 Uploading to YouTube..." |
| 2:45 PM | "🎉 UPLOAD COMPLETE! → goes live at 5PM IST" |

---

## 🗂️ Project Structure

```
max-lyrical-hub/
├── .github/
│   └── workflows/
│       └── automation.yml          # GitHub Actions cron jobs
├── scripts/
│   ├── 1_monitor_channels.py       # Scan channels, pick top 5
│   ├── 2_download_videos.py        # Playwright download via yt5s.biz
│   ├── 3_add_watermark.py          # FFmpeg watermark overlay
│   ├── 4_generate_seo.py           # OpenRouter AI SEO
│   └── 5_upload_youtube.py         # YouTube API upload + thumbnail
├── watermark/
│   └── watermark.png               # Max Lyrical Hub logo (no bg)
├── state/
│   ├── seen_videos.json            # Videos already processed
│   └── download_queue.json         # Current processing queue
├── setup_oauth.py                  # One-time OAuth setup (run locally)
├── requirements.txt
└── README.md
```

---

## ⚠️ Important Notes

- **Never commit** `client_secrets.json` or `yt_oauth.json` to GitHub
- YouTube API quota: 10,000 units/day per key. With 4 keys = 40,000 units — plenty
- GitHub Actions free tier: 2,000 minutes/month — enough for daily runs
- Videos are **scheduled** as private first, then auto-publish at peak times
- The bot respects YouTube's Terms of Service — only downloads public content
