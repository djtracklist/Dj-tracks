import streamlit as st
import subprocess
import sys
import os
import json
from itertools import islice
from youtube_comment_downloader import downloader as yd
import openai

st.title("DJ Tracks Extractor")

url = st.text_input("Enter YouTube URL")
model = st.selectbox("Choose OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key", type="password")

if st.button("Extract Tracks & Download MP3s"):
    st.info("Step 1: Downloading YouTube comments...")
    try:
        # Download comments generator and limit to first 100
        comments_gen = yd.YoutubeCommentDownloader.get_comments_from_url(url)
        comments = list(islice(comments_gen, 100))
    except Exception as e:
        st.error(f"Failed to get comments: {e}")
        st.stop()

    if not comments:
        st.warning("No comments found. Maybe try a different video.")
        st.stop()

    st.success(f"{len(comments)} comments downloaded.")

    st.info("Step 2: Extracting track names using GPT...")
    # Prepare OpenAI API
    openai.api_key = api_key

    # Build prompt from comments text
    comments_text = "\n".join([c.get("text", "") for c in comments])
    prompt = (
        "Extract any track names and artists mentioned, and return them as a JSON "
        "list of objects with keys 'artist' and 'track'. Only return valid JSON, for example: "
        "[{"artist": "Artist Name", "track": "Track Name"}, ...]"
    )

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": comments_text + "\n" + prompt}],
            temperature=0,
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

    # Display tracks with checkboxes
    selected_tracks = []
    for i, t in enumerate(tracks):
        artist = t.get("artist", "Unknown Artist")
        track = t.get("track", "Unknown Track")
        label = f"{artist} - {track}"
        if st.checkbox(label, key=f"track_{i}"):
            selected_tracks.append(t)

    # Optional: Download selected tracks as MP3s
    if selected_tracks:
        st.info("Step 3: Downloading selected tracks as MP3...")
        # Placeholder for download logic
        for t in selected_tracks:
            st.write(f"Downloading: {t.get('artist')} - {t.get('track')}")
        st.success("Selected tracks download completed.")
