#!/usr/bin/env python3
"""
ONE-TIME SETUP SCRIPT — Run this on your LOCAL machine
Generates the YT_OAUTH_JSON you need to add as a GitHub secret.

Run: python setup_oauth.py
"""

import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

def main():
    print("\n" + "="*60)
    print("MAX LYRICAL HUB — YouTube OAuth Setup")
    print("="*60)
    print()
    print("This script generates the OAuth credentials for uploading")
    print("videos to your 'Max Lyrical Hub' YouTube channel.")
    print()
    print("BEFORE RUNNING:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a project (or use existing)")
    print("3. Enable YouTube Data API v3")
    print("4. Create OAuth 2.0 credentials (Desktop App type)")
    print("5. Download the credentials JSON file")
    print("6. Rename it to 'client_secrets.json' in this folder")
    print()

    if not os.path.exists("client_secrets.json"):
        print("❌ ERROR: client_secrets.json not found!")
        print("   Download it from Google Cloud Console and place it here.")
        return

    print("✅ Found client_secrets.json")
    print()
    print("A browser window will open. Log in with:")
    print("  generalpurposeemailforuses@gmail.com")
    print("  (The account that owns Max Lyrical Hub)")
    print()
    input("Press ENTER to continue and open browser...")

    flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    # Build the JSON to store as secret
    oauth_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    oauth_json_str = json.dumps(oauth_data, indent=2)

    print()
    print("="*60)
    print("✅ SUCCESS! Your OAuth credentials are ready.")
    print("="*60)
    print()
    print("Copy the text below and add it as a GitHub secret named:")
    print("  YT_OAUTH_JSON")
    print()
    print("─"*60)
    print(oauth_json_str)
    print("─"*60)
    print()

    # Also save to file
    with open("yt_oauth.json", "w") as f:
        f.write(oauth_json_str)
    print("✅ Also saved to: yt_oauth.json")
    print()
    print("NEXT STEPS:")
    print("1. Go to your GitHub repo → Settings → Secrets and variables → Actions")
    print("2. Click 'New repository secret'")
    print("3. Name: YT_OAUTH_JSON")
    print("4. Value: paste the JSON above")
    print("5. Add all other secrets listed in README.md")
    print()
    print("⚠️  IMPORTANT: Add yt_oauth.json and client_secrets.json to .gitignore!")
    print("   Never commit these files to GitHub!")

if __name__ == "__main__":
    main()
