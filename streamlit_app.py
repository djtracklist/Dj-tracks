import streamlit as st
import subprocess
import sys
import os
import json
from itertools import islice

# Ensure dateparser is available
try:
    import dateparser
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "dateparser"])
    import dateparser

from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT
import openai

st.title("🎵 DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please provide a YouTube URL and OpenAI API key.")
        st.stop()

    st.info("Step 1: Downloading YouTube comments directly...")
    try:
        downloader = YoutubeCommentDownloader()
        raw_comments = list(islice(
            downloader.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT), 100
        ))
        comments = [c["text"] for c in raw_comments if "text" in c]

        if not comments:
            st.warning("No comments extracted. Try another video.")
            st.stop()

        st.success(f"{len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to get comments: {e}")
        st.stop()

    st.info("Step 2: Extracting track names using GPT...")
    openai.api_key = api_key

    comment_block = "\n".join(comments[:50])
    prompt = f"""You are an expert at identifying tracklists from DJ set YouTube comments.
The following are comments from a DJ set video. Extract track names and artists, one per line in the format 'Artist - Track'.

Comments:
{comment_block}
"""    

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response["choices"][0]["message"]["content"].strip()
        tracks = [line.strip("-•1234567890. ").strip() for line in result.split("\n") if "-" in line]
        st.success("Tracks identified:")
        for i, t in enumerate(tracks, 1):
            st.write(f"{i}. {t}")
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        st.stop()
