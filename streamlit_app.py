import streamlit as st
import subprocess
import sys
import os
import json
from itertools import islice
from youtube_comment_downloader import downloader as yd
import openai

# App title
st.title("DJ Set Track Extractor + MP3 Downloader")

# User inputs
youtube_url = st.text_input("Enter YouTube DJ Set URL:")
model_choice = st.selectbox("Choose OpenAI model:", options=["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    # Validate inputs
    if not youtube_url:
        st.error("Please enter a YouTube URL.")
        st.stop()
    if not api_key:
        st.error("Please enter your OpenAI API key.")
        st.stop()

    # Step 1: Download comments
    st.info("Step 1: Downloading YouTube comments directly...")
    downloader = yd.YoutubeCommentDownloader()
    comments_gen = downloader.get_comments_from_url(youtube_url, sort_by=yd.SORT_BY_RECENT)
    comments = list(islice(comments_gen, 200))  # limit to 200 comments
    if not comments:
        st.warning("No comments found. Maybe try a different video.")
        st.stop()
    st.success(f"{len(comments)} comments downloaded.")

    # Step 2: Extract track names via GPT
    st.info("Step 2: Extracting track names using GPT...")
    openai.api_key = api_key
    comment_block = "\n".join([c.get("text", "") for c in comments])
    prompt = (
        "Extract any track names and artists mentioned in the following YouTube comments. "
        "Return a JSON array of objects with 'artist' and 'track' keys. "
        "Be flexible with format, and include entries like:\n"
        '[{"artist":"Artist Name","track":"Track Title"}, ...]\n\n'
        "Comments:\n" + comment_block
    )

    try:
        response = openai.ChatCompletion.create(
            model=model_choice,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw_output = response.choices[0].message.content
    except Exception as e:
        st.error(f"OpenAI API request failed: {e}")
        st.stop()

    st.subheader("Raw GPT output")
    st.code(raw_output, language="json")

    # Parse JSON
    try:
        tracks = json.loads(raw_output)
    except json.JSONDecodeError:
        st.error("Failed to parse GPT output as JSON.")
        tracks = []

    if tracks:
        st.success("Tracks identified:")
        st.json(tracks)
    else:
        st.info("Tracklist")
        st.write("The comments do not provide specific artist and track information.")

    # Step 3: Optional MP3 download
    if tracks:
        if st.button("Download All Tracks as MP3"):
            st.info("Downloading MP3s...")
            for t in tracks:
                artist = t.get("artist", "Unknown Artist")
                track = t.get("track", "Unknown Track")
                title = f"{artist} - {track}"
                # sanitize filename
                safe_title = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in title)
                cmd = [
                    "yt-dlp",
                    "--extract-audio",
                    "--audio-format", "mp3",
                    "--output", f"{safe_title}.%(ext)s",
                    f"ytsearch1:{title}"
                ]
                subprocess.run(cmd, check=False)
            st.success("MP3 downloads complete.")
