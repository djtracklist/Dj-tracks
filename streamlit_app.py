import os
import json
import subprocess
import streamlit as st
import openai

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# --- Inputs ---
video_url = st.text_input("Enter YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
model = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

# Ensure download directory exists
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if st.button("Extract Tracks & Download MP3s"):
    # Validate
    if not video_url or not api_key:
        st.error("⚠️ Please enter both a YouTube URL and your OpenAI API key.")
        st.stop()

    # Step 1: Download comments via CLI
    st.info("Step 1: Downloading YouTube comments...")
    try:
        cmd = [
            "youtube-comment-downloader",
            "--url", video_url,
            "--sort", "recent",
            "--limit", "100"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        comments_data = json.loads(result.stdout)
        comments = [c.get("text", "") for c in comments_data]
        if not comments:
            raise ValueError("No comments returned by CLI.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Extract tracks via GPT
    st.info("Step 2: Extracting track names using GPT...")
    openai.api_key = api_key
    snippet = "\n".join(comments[:50])
    prompt = (
        "Extract any track names and artists mentioned in the text below, "
        "and return them as a JSON list of objects with fields 'artist' and 'track'.\n\n"
        "Comments:\n" + snippet
    )
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role":"user","content": prompt}],
            temperature=0
        )
        raw_output = resp.choices[0].message.content.strip()
        st.code(raw_output, language="json")
        tracks = json.loads(raw_output)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Empty or invalid JSON list.")
        st.success(f"✅ {len(tracks)} tracks identified.")
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    # Step 3: Display and select tracks
    st.write("---")
    st.write("### Select tracks to download")
    selected = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist", "").strip() or "Unknown Artist"
        track  = t.get("track", "").strip()  or "Unknown Track"
        label  = f"{artist} — {track}"
        if st.checkbox(label, key=idx, value=True):
            selected.append(label)

    # Step 4: Download selected tracks as MP3
    if selected:
        if st.button("Download Selected as MP3"):
            st.info("Step 4: Downloading selected tracks…")
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
            with __import__('yt_dlp').YoutubeDL(ydl_opts) as ydl:
                for q in selected:
                    st.write(f"▶️ Downloading: {q}")
                    try:
                        ydl.download([f"ytsearch1:{q}"])
                        st.write("✅ Done")
                    except Exception as e:
                        st.error(f"Failed to download {q}: {e}")
            st.success(f"🎉 All selected tracks downloaded to '{DOWNLOAD_DIR}/'.")
    else:
        st.info("No tracks selected for download.")
