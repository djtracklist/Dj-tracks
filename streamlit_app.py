import streamlit as st
import openai
import json
from itertools import islice
from youtube_comment_downloader import downloader as yd
import subprocess

st.title("DJ Tracks Extractor")

url = st.text_input("Enter YouTube URL")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not url or not api_key:
        st.error("Please provide both YouTube URL and API key.")
        st.stop()

    openai.api_key = api_key

    st.info("Step 1: Downloading YouTube comments...")
    try:
        downloader = yd.YoutubeCommentDownloader()
        comments_gen = downloader.get_comments_from_url(url)
        comments = list(islice(comments_gen, 100))
    except Exception as e:
        st.error(f"Failed to get comments: {e}")
        st.stop()
    if not comments:
        st.warning("No comments found. Maybe try a different video.")
        st.stop()
    st.success(f"{len(comments)} comments downloaded.")

    st.info("Step 2: Extracting track names using GPT...")
    comment_block = "\n".join(comments[:50])
    prompt = (
        f"Extract any track names and artists mentioned, and return them as a JSON list of objects "
        f"with 'artist' and 'track' keys. Be flexible with format, and include entries like:\n"
        f"[\n  {{"artist": "Artist Name", "track": "Track Title"}},\n  ...\n]\n\nComments:\n{comment_block}"
    )
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content
        tracks = json.loads(raw)
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        st.stop()

    if not tracks:
        st.warning("No tracks identified.")
        st.stop()

    st.success("Tracks identified:")

    selected = []
    st.write("Select tracks to download:")
    for i, item in enumerate(tracks):
        label = f"{item.get('artist', 'Unknown')} - {item.get('track', 'Unknown')}"
        if st.checkbox(label, key=f"track_{i}"):
            selected.append(label)

    if selected:
        st.info("Step 3: Downloading selected tracks...")
        for entry in selected:
            query = f"ytsearch1:{entry}"
            cmd = ["yt-dlp", "--extract-audio", "--audio-format", "mp3", query]
            subprocess.run(cmd, capture_output=True)
        st.success("Download completed.")
    else:
        st.info("No tracks selected for download.")
