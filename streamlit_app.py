import streamlit as st
import yt_dlp
import json
import os

from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

import openai

st.set_page_config(page_title="DJ Set Track Extractor", layout="wide")
st.title("🎧 DJ Set Tracklist & MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please provide both a YouTube URL and your OpenAI API key.")
        st.stop()

    st.info("Step 1: Downloading YouTube comments...")
    downloader = YoutubeCommentDownloader()
    try:
        comments = list(
            downloader.get_comments_from_url(
                video_url,
                sort_by=SORT_BY_POPULAR
            )
        )
    except Exception as e:
        st.error(f"Failed to fetch comments: {e}")
        st.stop()

    st.success(f"{len(comments)} comments downloaded.")

    comments_text = "\n".join(c["text"] for c in comments[:50])

    st.info("Step 2: Extracting track names using GPT…")
    prompt = f"""
Extract any track names and artists mentioned, and return them as a JSON list of objects with "artist" and "track" fields. Be flexible with format, and include entries like:

[
  {{ "artist": "Artist Name", "track": "Track Title" }},
  ...
]

Now parse this comment block below and output _only_ valid JSON:
"""
{comments_text}
"""
    openai.api_key = api_key
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{{"role": "user", "content": prompt.strip()}}]
        )
        raw_output = response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI request failed: {e}")
        st.stop()

    st.code(raw_output, language="json")

    try:
        tracks = json.loads(raw_output)
    except Exception:
        st.error("Failed to parse the JSON response from GPT.")
        st.stop()

    if not isinstance(tracks, list) or not tracks:
        st.warning("No tracks found in comments.")
        st.stop()

    st.subheader("✅ Select Tracks to Download")
    selected_tracks = []
    for idx, item in enumerate(tracks):
        artist = item.get("artist", "").strip()
        title = item.get("track", "").strip()
        label = f"{artist} – {title}" if artist and title else title or artist
        if st.checkbox(label, key=idx):
            selected_tracks.append(label)

    if selected_tracks:
        if st.button("Download Selected as MP3"):
            st.info("Downloading… this may take a moment.")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "quiet": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            os.makedirs("downloads", exist_ok=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for q in selected_tracks:
                    ydl.download([f"ytsearch1:{q}"])
            st.success("All selected tracks downloaded to the `downloads/` folder.")
    else:
        st.info("Select at least one track above to enable download.")
