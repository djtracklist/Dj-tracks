
import streamlit as st
import openai
from openai import OpenAI
import os
import json
from youtube_comment_downloader import downloader as yd

st.title("DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
model_choice = st.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s") and video_url and api_key:
    st.info("Step 1: Downloading YouTube comments directly...")

    try:
        comments = []
        for c in yd.YoutubeCommentDownloader().get_comments_from_url(video_url):
            comments.append(c["text"])
        if not comments:
            st.error("No comments found.")
        else:
            st.success(f"{len(comments)} comments downloaded.")

            st.info("Step 2: Extracting track names using GPT...")

            client = OpenAI(api_key=api_key)
            prompt = (
                "From the following YouTube comments, extract a list of distinct "
                "track names and their corresponding artists. Format as 'Track - Artist' if possible.\n\n"
                + "\n".join(comments[:100])
            )

            response = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            result = response.choices[0].message.content
            st.success("Tracks identified:")
            st.text(result)
    except Exception as e:
        st.error(f"An error occurred: {e}")
