# streamlit_app.py

import os
import io
import zipfile
import json
import re

import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

# ─── CONFIG ───────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY")
if not OPENAI_KEY:
    st.error("❌ Missing OpenAI API key in .streamlit/secrets.toml")
    st.stop()
openai.api_key = OPENAI_KEY

# ─── SIDEBAR ──────────────────────────────────────────────────────────
model_choice = st.sidebar.selectbox(
    "Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"], key="mdl"
)
limit = st.sidebar.number_input(
    "Max comments to fetch:", min_value=10, max_value=500, value=100, key="lim"
)
sort_option = st.sidebar.selectbox(
    "Sort comments by:", ["recent", "popular"], index=1, key="srt"
)  # default to "popular"

# ─── MAIN INPUT ───────────────────────────────────────────────────────
st.title("🎧 DJ Set Tracklist & MP3 Downloader")
video_url = st.text_input(
    "YouTube DJ Set URL",
    placeholder="https://www.youtube.com/watch?v=...",
    key="url"
)

if st.button("Extract Tracks", key="btn_extract"):
    if not video_url.strip():
        st.error("❌ Please enter a YouTube URL")
        st.stop()

    # 1) Download comments
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(
            video_url, sort_by=sort_flag
        )
        comments = [c.get("text", "") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ Downloaded {len(comments)} comments.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 2) GPT extraction
    st.info("Step 2: Extracting tracklist via GPT…")
    SYSTEM_PROMPT = """
You are a world‑class DJ‑set tracklist curator with exhaustive music knowledge.
Given raw YouTube comment text, do two things:
1) Extract timestamped track mentions in the form:
   MM:SS Artist - Title (optional remix/version) [label]
2) Extract any corrections (lines starting with "edit:", "correction:", etc.) as separate entries.

Return only a JSON object with exactly two keys:
{
  "tracks":    [ {artist, track, version, label}, … ],
  "corrections":[ {artist, track, version, label}, … ]
}
No extra keys or commentary.
"""
    FEW_SHOT = """
### Example Input:
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
10:00 edit: John Noseda - Climax (VIP Mix)

### Example JSON Output:
{
  "tracks":[
    {"artist":"John Noseda","track":"Climax","version":"","label":""},
    {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"}
  ],
  "corrections":[
    {"artist":"John Noseda","track":"Climax","version":"VIP Mix","label":""}
  ]
}
"""

    snippet = "\n".join(comments[:100])
    st.text_area("❯ Prompt sent to GPT (first 100 comments):", snippet, height=200, key="prompt")

    def extract_json(raw: str) -> str:
        txt = raw.strip()
        if txt.startswith("```"):
            parts = txt.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return txt

    def ask(model: str) -> str:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "assistant", "content": FEW_SHOT},
                {"role": "user",      "content": f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks, corrections, used_model = [], [], None
    for m in (model_choice, "gpt-3.5-turbo"):
        try:
            raw = ask(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks, corrections, used_model = parsed["tracks"], parsed["corrections"], m
                break
        except Exception:
            continue

    # fallback to regex if GPT fails
    if not used_model:
        st.warning("❌ GPT failed to extract any tracks or corrections — falling back to regex parsing.")

        pattern = re.compile(r'(\d{1,2}:\d{2})\s*([^-\n]+?)\s*-\s*([^
