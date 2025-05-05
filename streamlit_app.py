import streamlit as st
import json
import os
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT
import openai

st.title("🎧 DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please enter both a YouTube URL and OpenAI API key.")
        st.stop()

    with st.spinner("Step 1: Downloading YouTube comments..."):
        try:
            downloader = YoutubeCommentDownloader()
            raw_comments = downloader.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT)
            comments = [c["text"] for c in raw_comments if "text" in c]
            if not comments:
                st.warning("No comments found.")
                st.stop()
            st.success(f"{len(comments)} comments downloaded.")
        except Exception as e:
            st.error(f"Failed to get comments: {e}")
            st.stop()

    with st.spinner("Step 2: Extracting track names using GPT..."):
        try:
            openai.api_key = api_key
            prompt = (
                "Extract as many track names and artists as possible from the following DJ set YouTube comments. "
                "Be flexible with format, and include entries like:
"
                "- Artist - Track
"
                "- Track (if artist not known)
"
                "Here are the comments:

" +
                "\n".join(comments[:100])
            )
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            result = response["choices"][0]["message"]["content"].strip()
            st.success("Tracks identified:")
            st.text_area("Tracklist", result, height=300)
        except Exception as e:
            st.error(f"OpenAI API error: {e}")