import subprocess
import sys

# Ensure dateparser is installed
try:
    import dateparser
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "dateparser"])
    import dateparser

import streamlit as st
import openai
import json
import os
import subprocess

st.title("🎵 DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")

model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])

api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please enter both the YouTube URL and your OpenAI API key.")
    else:
        st.info("Processing...")

        st.markdown("**Step 1: Downloading YouTube comments...**")
        result = subprocess.run(
            ["python3", "-m", "youtube_comment_downloader", "--url", video_url,
             "--output", "comments/comments.json", "--pretty", "--limit", "200"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        st.text("STDOUT:")
        st.text(result.stdout)

        st.text("STDERR:")
        st.text(result.stderr)

        if not os.path.exists("comments/comments.json"):
            st.error("No comments were downloaded. Please check the YouTube URL or try a different video.")
        else:
            st.success("Comments downloaded successfully!")

            with open("comments/comments.json", "r", encoding="utf-8") as f:
                comments_data = json.load(f)

            comments_text = "\n".join(entry["text"] for entry in comments_data)

            prompt = (
                "You are an expert at recognising tracks from DJ sets based on comments.\n"
                "Extract any track names and artists mentioned, and return them as a list."
            )

            openai.api_key = api_key
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": comments_text}
                ]
            )

            extracted = response["choices"][0]["message"]["content"]
            st.markdown("### Suggested Tracks:")
            st.text(extracted)

            with open("tracks.txt", "w") as f:
                f.write(extracted)

            st.success("All done!")
