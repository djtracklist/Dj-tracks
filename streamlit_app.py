import streamlit as st
import openai
from openai import OpenAI
import yt_dlp
import re

# Set page config
st.set_page_config(page_title="DJ Set Track Extractor + MP3 Downloader", layout="centered")

# App title
st.title("🎶 DJ Set Track Extractor + MP3 Downloader")

# Inputs
video_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

# Download comments function
def get_youtube_comments(video_url, max_comments=100):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,
        'force_generic_extractor': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            comments = info.get("comments", [])
            return [c["text"] for c in comments[:max_comments]]
        except Exception as e:
            return []

# Call OpenAI with better prompt
def extract_tracks(comments, api_key, model):
    client = OpenAI(api_key=api_key)
    joined = "\n".join(comments)
    prompt = f"""
You are a music expert. Analyze the following YouTube comments from a DJ set video and extract as many distinct track names and/or artists as mentioned by commenters. Use whatever format you can infer (e.g. Artist - Track, Track by Artist, or even just Track if no artist is given). Be forgiving in format and avoid skipping entries that seem partial or ambiguous. Return a clean, deduplicated list in the format:

1. Track Name - Artist (if known)
2. Track Name (if artist not known)

Only include music-related references. Here are the comments:
"""
{joined}
"""
"""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# Main button action
if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please enter both the YouTube URL and your OpenAI API key.")
    else:
        with st.spinner("Step 1: Downloading YouTube comments directly..."):
            comments = get_youtube_comments(video_url)
            if comments:
                st.success(f"{len(comments)} comments downloaded.")
                with st.spinner("Step 2: Extracting track names using GPT..."):
                    result = extract_tracks(comments, api_key, model)
                    st.success("Tracks identified:")
                    st.markdown(result)
            else:
                st.error("Failed to retrieve YouTube comments. Please check the URL.")
