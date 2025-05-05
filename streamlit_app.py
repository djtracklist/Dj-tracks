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

# Input fields
video_url = st.text_input("Enter YouTube DJ Set URL", placeholder="https://youtu.be/...")
model = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

# Ensure downloads directory
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Main action
if st.button("Extract & Download"):
    # Validate inputs
    if not video_url or not api_key:
        st.error("Please enter both YouTube URL and OpenAI API key.")
        st.stop()

    # Step 1: Download comments
    st.info("Step 1: Downloading comments...")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT):
            comments.append(c.get("text", ""))
            if len(comments) >= 100:
                break
        if not comments:
            raise ValueError("No comments fetched.")
        st.success(f"{len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Comment download failed: {e}")
        st.stop()

    # Step 2: Try regex-based extraction first
    st.info("Step 2: Extracting tracks (regex fallback)...")
    regex = re.compile(r'(?:\d{1,2}:\d{2})\s*([^-–]+)[-–]\s*(.+)')
    extracted = []
    for text in comments:
        m = regex.search(text)
        if m:
            artist = m.group(1).strip()
            track = m.group(2).strip()
            extracted.append({"artist": artist, "track": track})
    # Deduplicate
    seen = set()
    tracks = []
    for item in extracted:
        key = (item['artist'], item['track'])
        if key not in seen:
            seen.add(key)
            tracks.append(item)
    if tracks:
        st.success(f"Found {len(tracks)} tracks via regex.")
    else:
        # Step 2b: Fall back to GPT
        st.info("No regex matches; extracting via GPT...")
        openai.api_key = api_key
        snippet = "\n".join(comments[:50])
        prompt = (
            "Extract any track names and artists mentioned below, "
            "and return as JSON array of {'artist','track'} objects.\n\n"
            "Comments:\n" + snippet
        )
        try:
            resp = openai.ChatCompletion.create(
                model=model,
                messages=[{"role":"user","content":prompt}],
                temperature=0
            )
            raw = resp.choices[0].message.content.strip()
            st.code(raw, language="json")
            tracks = json.loads(raw)
            if not isinstance(tracks, list) or not tracks:
                raise ValueError("Empty or invalid list")
            st.success(f"{len(tracks)} tracks identified via GPT.")
        except Exception as e:
            st.error(f"GPT extraction failed: {e}")
            st.stop()

    # Step 3: Select and download
    st.write("---")
    st.write("Select tracks to download:")
    selected = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist","").strip() or "Unknown Artist"
        track = t.get("track","").strip() or "Unknown Track"
        label = f"{artist} — {track}"
        if st.checkbox(label, key=idx, value=True):
            selected.append(label)

    if selected and st.button("Download Selected MP3s"):
        st.info("Downloading tracks...")
        ydl_opts = {
            "format":"bestaudio/best",
            "outtmpl":os.path.join(DOWNLOAD_DIR,"% (title)s.%(ext)s"),
            "noplaylist":True,
            "quiet":True,
            "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for q in selected:
                st.write(f"▶ {q}")
                try:
                    ydl.download([f"ytsearch1:{q}"])
                    st.write("✅ Done")
                except Exception as e:
                    st.error(f"Download failed: {e}")
        st.success(f"Tracks saved to '{DOWNLOAD_DIR}/'.")
    elif not selected:
        st.info("No tracks selected.")
