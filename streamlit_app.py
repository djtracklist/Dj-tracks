
import streamlit as st
import openai
import os
import json
from youtube_comment_downloader import YoutubeCommentDownloader

st.set_page_config(page_title="DJ Set Track Extractor + MP3 Downloader")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# Inputs
url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not url or not api_key:
        st.error("Please enter both a YouTube URL and your OpenAI API key.")
    else:
        # Step 1: download comments
        st.info("Step 1: Downloading YouTube comments...")
        try:
            downloader = YoutubeCommentDownloader()
            comments_generator = downloader.get_comments_from_url(url)
            comments = list(comments_generator)  # Convert generator to list
        except Exception as e:
            st.error(f"⚠️ Failed to download comments: {e}")
            st.stop()

        if not comments:
            st.warning("No comments found. Maybe try a different video or a live set URL.")
            st.stop()
        st.success(f"{len(comments)} comments downloaded.")

        # Step 2: extract tracks via GPT
        st.info("Step 2: Extracting track names using GPT...")
        openai.api_key = api_key

        snippet = "\n".join(c.get("text", "") for c in comments[:50])
        prompt = (
            "You are an expert at identifying tracklists from DJ sets. "
            "Extract any track names and artists mentioned, and return them as a JSON array "
            "of objects with fields 'artist' and 'track'.\n\n"
            + snippet
        )

        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            answer = response.choices[0].message.content
        except Exception as e:
            st.error(f"⚠️ OpenAI API error: {e}")
            st.stop()

        st.success("Tracks identified:")
        try:
            tracklist = json.loads(answer)
            st.json(tracklist)
        except json.JSONDecodeError:
            st.text_area("Raw GPT output", answer, height=200)

        # Step 3: (optional) Download MP3s
        st.info("Step 3: (Optional) Download MP3s")
        if st.button("Download All Tracks as MP3"):
            download_folder = "downloads"
            os.makedirs(download_folder, exist_ok=True)
            for obj in tracklist:
                query = f"{obj['artist']} {obj['track']}"
                outfile = os.path.join(download_folder, f"{obj['artist']} - {obj['track']}.mp3")
                try:
                    os.system(
                        f'yt-dlp "ytsearch1:{query}" '
                        f'-x --audio-format mp3 -o "{outfile}"'
                    )
                    st.write(f"✅ Downloaded: {obj['artist']} - {obj['track']}")
                except Exception as e:
                    st.write(f"❌ Failed: {query} ({e})")
            st.success(f"All done! Files in `{download_folder}/`.")
