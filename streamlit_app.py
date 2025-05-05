import streamlit as st
import subprocess
import sys
import os
import json
from youtube_comment_downloader import downloader
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# Force-install dateparser if not already available
subprocess.check_call([sys.executable, "-m", "pip", "install", "dateparser"])

# Import after ensuring installation
import dateparser
import yt_dlp
import openai

st.title("DJ Set Track Extractor + MP3 Downloader")

# User inputs
video_url = st.text_input("Enter YouTube DJ Set URL:")
model_choice = st.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please enter both a YouTube URL and an OpenAI API key.")
    else:
        st.info("Step 1: Downloading YouTube comments...")
        try:
            ytd = YoutubeCommentDownloader()
            comments = []
            for comment in ytd.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT, limit=100):
                comments.append(comment['text'])

            if not comments:
                st.error("No comments were downloaded. Please check the YouTube URL or try a different video.")
            else:
                st.success(f"{len(comments)} comments downloaded.")
                st.info("Step 2: Extracting tracks with GPT...")

                prompt = (
                    "The following are user comments from a DJ set video. "
                    "Extract any track names and artists mentioned, and return them as a list.

" +
                    "\n".join(comments)
                )

                openai.api_key = api_key
                response = openai.ChatCompletion.create(
                    model=model_choice,
                    messages=[{"role": "user", "content": prompt}]
                )

                tracks_text = response['choices'][0]['message']['content']
                st.text_area("Suggested Tracks", value=tracks_text, height=200)

                st.info("Step 3: Downloading MP3s...")
                output_dir = "downloads"
                os.makedirs(output_dir, exist_ok=True)
                tracks = [line.strip("-•1234567890. ").strip() for line in tracks_text.split("\n") if line.strip()]
                for track in tracks:
                    st.write(f"Downloading: {track}")
                    try:
                        subprocess.run([
                            "yt-dlp",
                            f"ytsearch1:{track}",
                            "--extract-audio",
                            "--audio-format", "mp3",
                            "-o", f"{output_dir}/%(title)s.%(ext)s"
                        ])
                    except Exception as e:
                        st.warning(f"Failed to download: {track} — {e}")
                st.success("All done!")

        except Exception as e:
            st.error(f"Error: {e}")
