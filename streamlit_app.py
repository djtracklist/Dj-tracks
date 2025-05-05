import os
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# App setup
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# Inputs
video_url = st.text_input("Enter YouTube DJ Set URL", placeholder="https://youtu.be/...")
model = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if st.button("Extract Tracks & Download MP3s"):
    # Validate inputs
    if not video_url or not api_key:
        st.error("⚠️ Please provide both a YouTube URL and your OpenAI API key.")
        st.stop()

    # Step 1: Download comments
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
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Extract tracks via GPT
    st.info("Step 2: Extracting track names using GPT...")
    openai.api_key = api_key
    snippet = "\n".join(comments[:50])
    prompt_base = (
        "Extract any track names and artists mentioned in the text below, "
        "and return them as a JSON array of objects with fields 'artist' and 'track'.\n\n"
        "Comments:\n"
    )
    # First try: full snippet
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt_base + snippet}],
            temperature=0
        )
    except UnicodeEncodeError:
        st.warning("Unicode encoding error with comments. Retrying with sanitized comments...")
        safe_snippet = snippet.encode('utf-8', 'ignore').decode('utf-8')
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt_base + safe_snippet}],
                temperature=0
            )
        except Exception as e:
            st.warning("Still failed with snippet. Retrying without comments...")
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": "Extract any track names and artists from a DJ set."}],
                temperature=0
            )
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        st.stop()

    raw_output = response.choices[0].message.content.strip()
    st.code(raw_output, language="json")
    try:
        tracks = json.loads(raw_output)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Parsed JSON invalid or empty.")
        st.success(f"✅ {len(tracks)} tracks identified.")
    except Exception as e:
        st.error(f"Failed to parse JSON: {e}")
        st.stop()

    # Step 3: Display and select
    st.write("---")
    st.write("### Select tracks to download")
    selected = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist", "").strip() or "Unknown Artist"
        track = t.get("track", "").strip() or "Unknown Track"
        label = f"{artist} — {track}"
        if st.checkbox(label, key=idx, value=True):
            selected.append(label)

    # Step 4: Download
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
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for q in selected:
                    st.write(f"▶️ Downloading: {q}")
                    try:
                        ydl.download([f"ytsearch1:{q}"])
                        st.write("✅ Done")
                    except Exception as e:
                        st.error(f"Failed to download {q}: {e}")
            st.success(f"All selected tracks downloaded to '{DOWNLOAD_DIR}/'.")
    else:
        st.info("No tracks selected.")
