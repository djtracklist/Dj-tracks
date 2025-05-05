import streamlit as st
import json
import yt_dlp
import openai
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader")
st.title("🎧 DJ Set Tracklist & MP3 Downloader")

# Inputs
url = st.text_input("Enter YouTube URL of the DJ set:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks"):
    # Step 1: Download comments
    st.info("Step 1: Downloading YouTube comments directly...")
    try:
        downloader = YoutubeCommentDownloader()
        raw = downloader.get_comments_from_url(
            url,
            sort_by=SORT_BY_RECENT,
            max_comments=100
        )
        comments = [c["text"] for c in raw]
        st.success(f"{len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Extract tracklist
    st.info("Step 2: Extracting track names using GPT...")
    openai.api_key = api_key
    prompt = (
        "Extract any track names and artists mentioned, and return them as a JSON list of objects "
        'like [{"artist": "Artist Name", "track": "Track Title"}, ...]. '
        "Be flexible with format, include remix info if present, and fill artist as an empty string if unknown."
    )
    comment_block = "\n".join(comments[:50])
    full_prompt = comment_block + "\n\n" + prompt

    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": full_prompt}]
        )
        raw_output = resp.choices[0].message.content
        st.code(raw_output, language="json")
        tracks = json.loads(raw_output)
    except Exception as e:
        st.error(f"Failed to parse GPT output: {e}")
        st.stop()

    # Step 3: Display & select
    st.info("Step 3: Select which tracks to download")
    selections = []
    for i, t in enumerate(tracks):
        col1, col2 = st.columns([0.1, 0.9])
        if col1.checkbox("", key=i):
            selections.append(t)
        col2.write(f"**{t.get('artist','')}** — {t.get('track','')}")

    # Download button
    if selections:
        if st.button("Download Selected as MP3"):
            st.info("Downloading…")
            for t in selections:
                artist = t.get("artist", "Unknown")
                track  = t.get("track",  "Unknown")
                safe_name = f"{artist} - {track}".replace("/", "_")
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": f"mp3s/{safe_name}.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192"
                    }],
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                except Exception as e:
                    st.error(f"Error downloading {safe_name}: {e}")
            st.success("✅ All selected tracks downloaded.")
    else:
        st.warning("No tracks selected.")
