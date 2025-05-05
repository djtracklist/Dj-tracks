import os
import json
import streamlit as st
import yt_dlp
import openai

# ----- MONKEY-PATCH requests to sanitize ALL headers -----
import requests
from requests.sessions import Session as _Session
_orig_request = _Session.request

def _safe_request(self, method, url, **kwargs):
    # Sanitize header values to Latin-1
    headers = kwargs.get("headers", {})
    safe_headers = {}
    for k, v in headers.items():
        if isinstance(v, str):
            safe_headers[k] = v.encode("latin-1", "ignore").decode("latin-1")
        else:
            safe_headers[k] = v
    kwargs["headers"] = safe_headers
    return _orig_request(self, method, url, **kwargs)

_Session.request = _safe_request
# ---------------------------------------------------------

from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# --- App Configuration ---
st.set_page_config(page_title="DJ Tracklist & MP3 Downloader", layout="centered")
st.title("DJ Tracklist & MP3 Downloader")  # no emojis here

# --- Inputs ---
video_url = st.text_input(
    "Enter YouTube DJ Set URL",
    placeholder="https://www.youtube.com/watch?v=..."
)
model = st.selectbox(
    "Choose OpenAI model",
    ["gpt-4", "gpt-3.5-turbo"]
)
api_key = st.text_input(
    "Enter your OpenAI API Key",
    type="password"
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Main Action ---
if st.button("Extract Tracks & Download MP3s"):
    # 0. Validate
    if not video_url or not api_key:
        st.error("Please provide both the YouTube URL and your OpenAI API key.")
        st.stop()

    # 1. Download comments via Python API
    st.info("Step 1: Downloading YouTube comments...")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT):
            comments.append(c.get("text", ""))
            if len(comments) >= 100:
                break
        if not comments:
            raise ValueError("No comments returned.")
        st.success(f"{len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 2. Extract tracklist via GPT
    st.info("Step 2: Extracting track names with GPT...")
    openai.api_key = api_key
    snippet = "\n".join(comments[:50])
    prompt = (
        "Extract any track names and artists mentioned below, "
        "and return them as a JSON array of objects with fields "
        "'artist' and 'track'.\n\nComments:\n" + snippet
    )
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
    except Exception as e:
        st.error(f"OpenAI request failed: {e}")
        st.stop()

    raw_output = response.choices[0].message.content.strip()
    st.code(raw_output, language="json")
    try:
        tracks = json.loads(raw_output)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Parsed JSON is empty or not a list.")
        st.success(f"{len(tracks)} tracks identified.")
    except Exception as e:
        st.error(f"Failed to parse GPT output: {e}")
        st.stop()

    # 3. Display & select
    st.write("---")
    st.write("Select tracks to download:")
    selected = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist", "").strip() or "Unknown Artist"
        track  = t.get("track",  "").strip() or "Unknown Track"
        label  = f"{artist} — {track}"
        if st.checkbox(label, key=idx, value=True):
            selected.append(label)

    # 4. Download MP3s
    if selected:
        if st.button("Download Selected as MP3"):
            st.info("Downloading tracks...")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for q in selected:
                    st.write(f"▶ {q}")
                    try:
                        ydl.download([f"ytsearch1:{q}"])
                    except Exception as e:
                        st.error(f"Failed to download {q}: {e}")
            st.success(f"All selected tracks downloaded to '{DOWNLOAD_DIR}/'.")
    else:
        st.info("No tracks selected for download.")
