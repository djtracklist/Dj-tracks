import os
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

st.set_page_config(page_title="DJ Set Tracklist + MP3s", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# --- Inputs ---
video_url = st.text_input("Enter YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
model = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please provide both a YouTube URL and your OpenAI API key.")
        st.stop()

    # Step 1: fetch comments
    st.info("Step 1: Downloading YouTube comments directly…")
    try:
        downloader = YoutubeCommentDownloader()
        raw_comments = []
        for c in downloader.get_comments_from_url(video_url, sort=SORT_BY_POPULAR, limit=100):
            raw_comments.append(c["text"])
        st.success(f"{len(raw_comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: extract tracks via GPT
    st.info("Step 2: Extracting track names using GPT…")
    openai.api_key = api_key
    prompt = (
        "Extract any track names and artists mentioned in the text below, "
        "and return them as a JSON array of objects with fields "
        '"artist" and "track".\n\nComments:\n'
        + "\n".join(raw_comments[:50])
    )
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content
        tracks = json.loads(content)
        st.success("Tracks identified:")
    except Exception as e:
        st.error("GPT step failed or returned invalid JSON.")
        st.code(content if "content" in locals() else str(e))
        st.stop()

    # display with checkboxes
    st.write("---")
    st.write("### Select tracks to download")
    to_download = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist", "").strip()
        track  = t.get("track", "").strip()
        label  = f"{artist} — {track}"
        if st.checkbox(label, key=idx):
            to_download.append(label)

    # Step 3: download selected
    if to_download:
        st.info("Step 3: Downloading selected tracks as MP3…")
        out_dir = "downloads"
        os.makedirs(out_dir, exist_ok=True)
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for title in to_download:
                st.write(f"Downloading **{title}** …")
                try:
                    ydl.download([f"ytsearch1:{title}"])
                    st.write("✅ Done")
                except Exception as e:
                    st.error(f"Failed to download {title}: {e}")
        st.success("All selected downloads complete!")
    else:
        st.info("No tracks selected for download.")
