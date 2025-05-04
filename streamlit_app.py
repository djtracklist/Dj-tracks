
import streamlit as st
import subprocess
import json
import openai
import yt_dlp
import os

st.set_page_config(page_title="DJ Set Track Extractor", layout="wide")
st.title("DJ Set Track Extractor + MP3 Downloader")

# Inputs
video_url = st.text_input("Enter YouTube DJ Set URL:")
model_choice = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")
run_button = st.button("Extract Tracks & Download MP3s")

if run_button and video_url and api_key:
    st.info("Processing...")

    # Step 1: Download Comments
    st.write("Step 1: Downloading YouTube comments...")
    video_id = video_url.split("v=")[-1].split("&")[0] if "v=" in video_url else video_url.split("/")[-1]
    os.makedirs("comments", exist_ok=True)
    subprocess.run([
        "python3", "-m", "youtube_comment_downloader",
        "--youtubeid", video_id,
        "--output", "../comments/comments.json",
        "--sort", "0",
        "--limit", "100"
    ], cwd="youtube-comment-downloader")

    # Step 2: Load comments
    st.write("Step 2: Extracting track names using GPT...")
    with open("comments/comments.json", "r", encoding="utf-8") as f:
        comments = [json.loads(line)["text"] for line in f]

    prompt = (
        "Extract a list of artist and track names mentioned in this DJ set's YouTube comments.\n"
        "Use format: 'Artist - Track'. Only include lines where you're confident a track is mentioned.\n\n"
        + "\n".join(comments[:30])
    )

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model_choice,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    tracks = response.choices[0].message.content.strip().splitlines()
    st.success("Tracks extracted:")
    for t in tracks:
        st.write("-", t)

    # Step 3: Download MP3s
    st.write("Step 3: Downloading MP3s with yt-dlp...")
    os.makedirs("downloads", exist_ok=True)

    for track in tracks:
        if "-" not in track:
            continue
        st.write(f"Downloading: {track}")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'downloads/{track}.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([f"ytsearch1:{track}"])
            except Exception as e:
                st.warning(f"Failed to download {track}: {e}")

    st.success("All done! Check the 'downloads' folder for your MP3s.")
