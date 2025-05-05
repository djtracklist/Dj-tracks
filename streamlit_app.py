import streamlit as st
import os
import subprocess
import json
import openai

st.title("🎵 DJ Set Track Extractor + MP3 Downloader")

youtube_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    with st.spinner("Processing..."):

        # Step 1: Download comments
        st.markdown("### Step 1: Downloading YouTube comments...")
        result = subprocess.run([
            "python3", "-m", "youtube_comment_downloader",
            "--url", youtube_url,
            "--output", "comments/comments.json",
            "--limit", "200"
        ], capture_output=True, text=True)

        st.text("STDOUT:")
        st.code(result.stdout)
        st.text("STDERR:")
        st.code(result.stderr)

        # Check if file was created
        if not os.path.exists("comments/comments.json"):
            st.error("No comments were downloaded. Please check the YouTube URL or try a different video.")
            st.stop()

        # Step 2: Extract track names using OpenAI
        st.markdown("### Step 2: Extracting Track Names...")
        with open("comments/comments.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        comments = [entry["text"] for entry in data]
        joined_comments = "\n".join(comments[:50])  # limit for prompt size

        openai.api_key = api_key
        prompt = f"""
You are a helpful assistant for extracting tracklists from DJ sets. The following are YouTube comments on a DJ set video.

Extract any track names and artists mentioned, and return them as a list. 
Avoid repetitions. Ignore irrelevant comments.

Comments:
{joined_comments}
"""

        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            extracted = response.choices[0].message["content"]
            st.markdown("### Suggested Tracks:")
            st.code(extracted)
        except Exception as e:
            st.error(f"OpenAI API Error: {e}")
            st.stop()
