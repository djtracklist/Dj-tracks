import streamlit as st
import os
import subprocess
import json
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT
from openai import OpenAI
import yt_dlp

# -- UI --
st.title("DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
limit = st.slider("Number of comments to fetch", min_value=10, max_value=200, value=50, step=10)
model = st.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    # Step 1: Download comments
    st.info("Step 1: Downloading YouTube comments...")
    try:
        video_id = video_url.split('v=')[-1].split('&')[0]
        ytc = YoutubeCommentDownloader()
        comments = ytc.get_comments_from_url(video_id, sort_by=SORT_BY_RECENT, limit=limit)
        st.success(f"{len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Prepare comment text block
    comments_text = "\n".join(c['text'] for c in comments)

    # Step 2: Extract tracks via GPT
    st.info("Step 2: Extracting track names using GPT...")
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""Extract an array of JSON objects from the following comments text. Each object should have 'artist' and 'track' fields, and list only distinct tracks. Return valid JSON only:

Comments:
""" + comments_text
        response = client.chat.completions.create(
            model=model,
            messages=[{"role":"user","content":prompt}],
        )
        result = response.choices[0].message.content
        tracks = json.loads(result)
        st.success("Tracks identified:")
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    # Display and select tracks
    st.subheader("Step 3: (Optional) Download MP3s")
    selections = []
    for idx, t in enumerate(tracks):
        label = f"{t.get('artist','Unknown')} - {t.get('track','Unknown')}"
        if st.checkbox(label, key=f"chk_{idx}", value=True):
            selections.append(label)
    if st.button("Download Selected MP3s"):
        st.info("Downloading selected tracks...")
        for song in selections:
            st.write(f"Downloading: {song}")
            # yt-dlp download
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join('downloads', f"{song}.%(ext)s"),
                'noplaylist': True,
                'quiet': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            }
            os.makedirs('downloads', exist_ok=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([f"ytsearch1:{song}"])
                except Exception as de:
                    st.error(f"Download failed for {song}: {de}")
        st.success("All selected downloads complete!")