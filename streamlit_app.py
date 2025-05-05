# Monkey-patch requests to enforce ASCII header values
import requests
_orig_default_headers = requests.utils.default_headers
def _ascii_default_headers():
    hdrs = _orig_default_headers()
    for k, v in list(hdrs.items()):
        try:
            # Force header values to Latin-1, dropping non-Latin-1 chars
            hdrs[k] = v.encode('latin-1', 'ignore').decode('latin-1')
        except Exception:
            hdrs[k] = ''
    return hdrs
requests.utils.default_headers = _ascii_default_headers

import os
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# App configuration
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# Inputs
video_url = st.text_input("Enter YouTube DJ Set URL", placeholder="https://youtu.be/...")
model = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("⚠️ Provide both a YouTube URL and your OpenAI API key.")
        st.stop()

    # Step 1: Fetch comments via Python API
    st.info("Step 1: Downloading YouTube comments...")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT):
            comments.append(c.get("text",""))
            if len(comments) >= 100:
                break
        if not comments:
            raise ValueError("No comments returned.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Extract via GPT with robust fallback
    st.info("Step 2: Extracting track names via GPT...")
    openai.api_key = api_key
    snippet = "\n".join(comments[:50])
    prompt_body = (
        "Extract any track names and artists mentioned below, "
        "and return them as a JSON array of objects with keys 'artist' and 'track'.\n\n"
        "Comments:\n"
    )
    # Try full snippet
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role":"user","content":prompt_body + snippet}],
            temperature=0
        )
    except UnicodeEncodeError:
        st.warning("Dropped non-Latin-1 chars and retrying...")
        safe = snippet.encode('latin-1','ignore').decode('latin-1')
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role":"user","content":prompt_body + safe}],
            temperature=0
        )
    except Exception as e:
        st.warning(f"Snippet failed: {e}\nRetrying without comments...")
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role":"user","content":(
                "Extract any track names and artists from a DJ set "
                "and return JSON of {artist, track} list."
            )}],
            temperature=0
        )

    raw = response.choices[0].message.content.strip()
    st.code(raw, language="json")
    try:
        tracks = json.loads(raw)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Empty or invalid JSON list")
        st.success(f"✅ {len(tracks)} tracks identified.")
    except Exception as e:
        st.error(f"JSON parse error: {e}")
        st.stop()

    # Step 3: Display & select
    st.write("---")
    st.write("### Select tracks to download")
    selected = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist","").strip() or "Unknown Artist"
        track  = t.get("track","").strip()  or "Unknown Track"
        label  = f"{artist} — {track}"
        if st.checkbox(label, key=idx, value=True):
            selected.append(label)

    # Step 4: Download MP3s
    if selected and st.button("Download Selected as MP3"):
        st.info("Step 4: Downloading selected tracks…")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            for q in selected:
                st.write(f"▶️ {q}")
                try:
                    ydl.download([f"ytsearch1:{q}"])
                    st.write("✅ Done")
                except Exception as e:
                    st.error(f"Download failed: {e}")
        st.success(f"All selected tracks in '{DOWNLOAD_DIR}/'.")
    elif not selected:
        st.info("No tracks selected for download.")
