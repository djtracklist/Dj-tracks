import os
import re
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# App config
st.set_page_config(page_title="DJ Tracklist & MP3 Downloader", layout="centered")
st.title("DJ Tracklist Extractor & MP3 Downloader")

# User inputs
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

# Ensure download folder exists
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if st.button("Extract & Download"):
    # 1. Validate inputs
    if not video_url or not api_key:
        st.error("Please enter both the YouTube URL and your OpenAI API key.")
        st.stop()

    # 2. Download comments
    st.info("Step 1: Downloading comments…")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT):
            comments.append(c.get("text", ""))
            if len(comments) >= 100:
                break
        if not comments:
            raise RuntimeError("No comments fetched.")
        st.success(f"{len(comments)} comments fetched.")
    except Exception as e:
        st.error(f"Failed to fetch comments: {e}")
        st.stop()

    # 3. Attempt regex extraction
    st.info("Step 2: Extracting via regex…")
    patterns = [
        re.compile(r'^\s*\d{1,2}:\d{2}\s*([^-–\n]+)[-–]\s*(.+)$'),  # timestamped
        re.compile(r'^\s*([^-–\n]+)[-–]\s*(.+)$'),                 # plain Artist–Track
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

    # 4. If no regex hits, fall back to GPT
    if tracks:
        st.success(f"Found {len(tracks)} tracks via regex.")
    else:
        st.info("No regex matches—falling back to GPT…")
        openai.api_key = api_key
        snippet = "\n".join(comments[:50])
        prompt = (
            "Extract every track mention (artist and track title) from the following YouTube comments "
            "and return a JSON array of objects with fields 'artist' and 'track'.\n\n"
            f"Comments:\n{snippet}"
        )
        st.code(prompt, language="markdown")
        try:
            resp = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            raw = resp.choices[0].message.content.strip()
            st.code(raw, language="json")
            tracks = json.loads(raw)
            if not isinstance(tracks, list) or not tracks:
                raise ValueError("Empty or invalid JSON list.")
            st.success(f"Found {len(tracks)} tracks via GPT.")
        except Exception as e:
            st.error(f"GPT extraction failed: {e}")
            st.stop()

    # 5. Show checkbox list
    st.write("---")
    st.write("Select tracks to download:")
    selected = []
    for i, t in enumerate(tracks):
        artist = t.get("artist", "").strip() or "Unknown Artist"
        track  = t.get("track", "").strip()  or "Unknown Track"
        label  = f"{artist} — {track}"
        if st.checkbox(label, key=i, value=True):
            selected.append(label)

    # 6. Download selected MP3s
    if selected:
        if st.button("Download Selected MP3s"):
            st.info("Downloading MP3s…")
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
                        st.write("Done")
                    except Exception as e:
                        st.error(f"Download failed for {q}: {e}")
            st.success("All selected tracks saved to the downloads folder.")
    else:
        st.info("No tracks selected.")
