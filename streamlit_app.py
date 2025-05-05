import streamlit as st
import json
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT
import openai

st.title("🎵 DJ Set Track Extractor + MP3 Downloader")

url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s") and url and api_key:
    with st.spinner("Step 1: Downloading YouTube comments..."):
        downloader = YoutubeCommentDownloader()
        try:
            comments = [c["text"] for c in downloader.get_comments_from_url(url, sort_by=SORT_BY_RECENT)]
            st.success(f"{len(comments)} comments downloaded.")
        except Exception as e:
            st.error(f"Failed to get comments: {e}")
            st.stop()

    with st.spinner("Step 2: Extracting track names using GPT..."):
        openai.api_key = api_key
        prompt = f"""Extract a list of distinct song titles and artists from the following YouTube comments. 
Only return track names and their corresponding artist if clearly mentioned, without extra text or formatting.

Comments:
{json.dumps(comments[:100])}

Return the result as a simple list with this format:
Artist - Track Name"""

        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            output = response["choices"][0]["message"]["content"]
            st.success("Tracks identified:")
            st.text_area("Tracklist", output, height=300)
        except Exception as e:
            st.error(f"OpenAI API error: {e}")