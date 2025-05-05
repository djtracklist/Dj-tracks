
import streamlit as st
import os
import json
import subprocess
import yt_dlp
import openai
import re
from collections import Counter

# Set up Streamlit UI
st.title("DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s") and video_url and api_key:
    st.info("Processing...")
    openai.api_key = api_key

    # Extract video ID
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_url)
    if not match:
        st.error("Invalid YouTube URL.")
        st.stop()
    video_id = match.group(1)

    os.makedirs("comments", exist_ok=True)
    comments_path = "comments/comments.json"

    # Step 1: Download comments
    st.write("Step 1: Downloading YouTube comments...")
    result = subprocess.run([
        "python3", "-m", "youtube_comment_downloader",
        "--youtubeid", video_id,
        "--output", comments_path,
        "--limit", "200",
        "--sort", "popular"
    ], capture_output=True, text=True)

    st.text("STDOUT:\n" + result.stdout)
    st.text("STDERR:\n" + result.stderr)

    if not os.path.exists(comments_path):
        st.error("No comments were downloaded. Please check the YouTube URL or try a different video.")
        st.stop()

    # Step 2: Load comments
    with open(comments_path, "r", encoding="utf-8") as f:
        try:
            comments_json = json.load(f)
        except json.JSONDecodeError:
            st.error("Failed to parse comments JSON.")
            st.stop()
    comments = [entry["text"] for entry in comments_json]

    # Step 3: Use LLM to extract track suggestions
    st.write("Step 2: Extracting track list using OpenAI...")

    joined_comments = "\n".join(comments[:100])
    prompt = f"""
A DJ set was uploaded to YouTube. The top comments are below. Extract any track names and artists mentioned. 
Just list them in the format 'Artist - Track', one per line. Be strict — only include lines that clearly describe a track.

{joined_comments}
"""

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        st.stop()

    raw_text = response.choices[0].message.content.strip()
    track_lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    st.write("Suggested Tracks:")
    for i, track in enumerate(track_lines, 1):
        st.write(f"{i}. {track}")

    # Step 4: Download tracks as MP3s
    st.write("Step 3: Downloading MP3s...")

    def download_song_mp3(song_title, output_dir="downloads"):
        output_template = os.path.join(output_dir, f"{song_title}.%(ext)s")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'noplaylist': True,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        os.makedirs(output_dir, exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([f"ytsearch1:{song_title}"])
                return True
            except Exception:
                return False

    for track in track_lines:
        st.write(f"Downloading: {track}")
        success = download_song_mp3(track)
        if not success:
            st.warning(f"Failed to download: {track}")

    st.success("All done!")
