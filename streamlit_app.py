import streamlit as st
import subprocess
import json
import re
import tempfile
import os
import openai

st.set_page_config(page_title="DJ Tracklist Extractor", layout="wide")

st.title("DJ Tracklist Extractor")

# --- Sidebar Inputs ---
model = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.sidebar.text_input("Enter your OpenAI API Key:", type="password")

url = st.text_input("YouTube URL:", value="https://www.youtube.com/watch?v=")
limit = st.number_input("Max comments to fetch:", min_value=10, max_value=500, value=100)
download_mp3 = st.checkbox("Enable MP3 download", value=False)

if st.button("Extract Tracks & Download MP3s"):
    if not api_key:
        st.error("Please enter your OpenAI API key.")
        st.stop()

    openai.api_key = api_key

    # Step 1: Download comments
    st.info("Step 1: Downloading YouTube comments…")
    cmd = [
        "youtube-comment-downloader",
        "--url", url,
        "--limit", str(limit),
        "--sort", "recent",
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        comments = output.decode("utf-8", errors="ignore").splitlines()
        st.success(f"{len(comments)} comments downloaded.")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to download comments:\n{e.output.decode('utf-8', errors='ignore')}")
        st.stop()

    # Step 2: Extract tracks via GPT
    st.info("Step 2: Extracting track names using GPT…")
    snippet = "\n".join(comments[:min(len(comments), 50)])
    safe_snippet = snippet.encode("ascii", errors="ignore").decode("ascii")

    prompt = (
        "Extract any track names and artists mentioned in the text below "
        "and return them as a JSON list of objects with fields "
        "'artist' and 'track'.\n\nComments:\n"
        + safe_snippet
    )

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw_output = response.choices[0].message.content.strip()
        st.code(raw_output, language="json")
        tracks = json.loads(raw_output)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Empty or invalid JSON list.")
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    # Display tracks with checkboxes
    st.success("Tracks identified:")
    selected = []
    for i, t in enumerate(tracks):
        label = f"{t.get('artist','?')} — {t.get('track','?')}"
        if st.checkbox(label, value=True, key=f"track_{i}"):
            selected.append(label)

    # Step 3: Download MP3s (optional)
    if download_mp3:
        if not selected:
            st.warning("No tracks selected for download.")
        else:
            st.info("Step 3: Downloading MP3s…")
            download_folder = tempfile.mkdtemp()
            for label in selected:
                artist, track = label.split(" — ", 1)
                query = f"{artist} {track}"
                filename = f"{artist}_{track}.mp3".replace(" ", "_")
                filepath = os.path.join(download_folder, filename)
                ytdlp_cmd = [
                    "yt-dlp",
                    "--extract-audio",
                    "--audio-format", "mp3",
                    "--output", filepath,
                    f"ytsearch1:{query}"
                ]
                try:
                    subprocess.check_call(ytdlp_cmd, stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    st.warning(f"Could not download: {label}")
            st.success(f"Downloaded {len(selected)} tracks to {download_folder}")