import os
import re
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# App configuration
st.set_page_config(page_title="DJ Tracklist + MP3 Downloader", layout="centered")
st.title("DJ Tracklist Extractor & MP3 Downloader")

# Inputs
video_url = st.text_input("Enter YouTube DJ Set URL", placeholder="https://youtu.be/...")
model    = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key  = st.text_input("Enter your OpenAI API Key", type="password")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if st.button("Extract & Download"):
    # Validate
    if not video_url or not api_key:
        st.error("Please enter both YouTube URL and OpenAI API key.")
        st.stop()

    # Step 1: Download comments
    st.info("Step 1: Downloading comments…")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT):
            comments.append(c.get("text",""))
            if len(comments) >= 100:
                break
        if not comments:
            raise RuntimeError("No comments fetched.")
        st.success(f"{len(comments)} comments fetched.")
    except Exception as e:
        st.error(f"Failed to fetch comments: {e}")
        st.stop()

    # Step 2: Regex-based extraction
    st.info("Step 2: Extracting tracks via regex…")
    patterns = [
        # e.g. "12:34 Artist – Track Title"
        re.compile(r'^\s*\d{1,2}:\d{2}\s*([^-–\n]+)[-–]\s*(.+)$'),
        # e.g. "Artist – Track Title"
        re.compile(r'^\s*([^-–\n]+)[-–]\s*(.+)$'),
    ]
    tracks = []
    seen = set()
    for line in comments:
        for pat in patterns:
            m = pat.search(line)
            if m:
                artist = m.group(1).strip()
                track  = m.group(2).strip()
                key = (artist.lower(), track.lower())
                if key not in seen:
                    seen.add(key)
                    tracks.append({"artist": artist, "track": track})
                break
    if tracks:
        st.success(f"✅ Found {len(tracks)} tracks via regex.")
    else:
        # Step 2b: GPT fallback
        st.info("No regex matches. Falling back to GPT…")
        openai.api_key = api_key
        snippet = "\n".join(comments[:50])
        prompt = f"""
You are an expert at reading YouTube comment tracklists. 
Extract every track mention (artist and track title) from the text below and output _only_ valid JSON like:

[
  {{ "artist": "Artist Name", "track": "Track Title" }},
  ...
]

Comments Block:
