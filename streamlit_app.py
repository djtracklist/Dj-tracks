import streamlit as st
import subprocess
import openai
import os
import json

st.title("🎧 DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not video_url or not api_key:
        st.error("Please provide both a YouTube URL and an OpenAI API key.")
    else:
        with st.container():
            st.info("Step 1: Downloading YouTube comments directly...")

            try:
                from youtube_comment_downloader.downloader import YoutubeCommentDownloader

                downloader = YoutubeCommentDownloader()
                comments_gen = downloader.get_comments_from_url(video_url)

                comments = []
                for count, comment in zip(range(50), comments_gen):  # Limit to 50 comments for clarity
                    comments.append(comment["text"])

                if not comments:
                    st.error("No comments found.")
                    st.stop()

                st.success(f"{len(comments)} comments downloaded.")

                st.info("Step 2: Extracting track names using GPT...")

                openai.api_key = api_key
                comment_block = "\n".join(comments)

                refined_prompt = f"""You are helping identify music tracks from comments under a DJ set video.

Each line should follow the format:
Artist - Track

Only list actual tracks (no guesses or vague mentions). If either the artist or track name is missing or unclear, skip the entry entirely.

Here are some YouTube comments from the DJ set:

{comment_block}

Extract the tracks:
"""    

                response = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": refined_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=600
                )

                tracks = response["choices"][0]["message"]["content"]
                if tracks.strip():
                    st.success("Tracks identified:")
                    st.markdown(tracks)
                else:
                    st.warning("No tracks were identified. Try another video.")

            except Exception as e:
                st.error(f"Failed to extract tracks: {e}")
