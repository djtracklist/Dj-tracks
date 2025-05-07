import os
import io
import zipfile
import json
import streamlit as st
import yt_dlp
from openai import OpenAI
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

# ── Streamlit config ───────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# ── Sidebar inputs ─────────────────────────────────────────────────
model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
limit = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])

# Use API key from secrets.toml
api_key = st.secrets["OPENAI_API_KEY"]

# ── Main UI ────────────────────────────────────────────────────────
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Extract Tracks", key="extract_btn"):
    if not api_key:
        st.error("OpenAI API key is missing from Streamlit secrets.")
        st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()

    # ── Step 1: Download comments ────────────────────────────────
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=sort_flag)
        comments = [c.get("text", "") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # ── Step 2: Use GPT to extract tracks ─────────────────────────
    st.info("Step 2: Extracting tracks via GPT…")
    client = OpenAI(api_key=api_key)

    system_prompt = """
You are a world‑class DJ‑set tracklist curator with a complete music knowledge base.
Given raw YouTube comment texts, do two things:
1) Extract all timestamped track mentions in the form:
   MM:SS Artist - Track Title (optional remix/version and [label])
2) Extract any correction/update comments where a user writes "edit:", "correction:", "update:", "oops:", etc., clarifying a previous track.

Return ONLY a JSON object with keys "tracks" and "corrections", each a list of objects with fields:
  artist  (string)
  track   (string)
  version (string or empty)
  label   (string or empty)
No extra keys or commentary.
"""

    few_shot = """
### Example Input:
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
07:20 Cormac - Sparks
10:00 edit: John Noseda - Climax (VIP Mix)

### Example JSON Output:
{
  "tracks": [
    {"artist":"John Noseda","track":"Climax","version":"","label":""},
    {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"},
    {"artist":"Cormac","track":"Sparks","version":"","label":""}
  ],
  "corrections": [
    {"artist":"John Noseda","track":"Climax","version":"VIP Mix","label":""}
  ]
}
"""

    snippet = "\n".join(comments[:100])
    st.text_area("❯ Prompt sent to GPT:", snippet, height=200)

    def extract_json(raw: str) -> str:
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def ask(model_name: str) -> str:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "assistant", "content": few_shot},
                {"role": "user", "content": f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks, corrections, used_model = [], [], None
    for m in [model_choice, "gpt-3.5-turbo"]:
        try:
            raw = ask(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model = m
                break
        except Exception:
            continue

    if used_model is None:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    all_entries = tracks + corrections
    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections via {used_model}.")
    st.session_state["dj_tracks"] = all_entries
