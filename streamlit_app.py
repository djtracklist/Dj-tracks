import os
import json

import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT

st.set_page_config(page_title="DJ Set Track Extractor + MP3 Downloader")
st.title("Downloader")

url = st.text_input("YouTube DJ Set URL")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download"):
    # ── STEP 1: Download comments ──
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        comments = []
        for c in downloader.get_comments_from_url(url, sort_by=SORT_BY_RECENT):
            # c is a dict; grab 'text'
            comments.append(c.get("text", ""))
            if len(comments) >= 100:
                break
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    st.success(f"✅ {len(comments)} comments downloaded.")
    comments_text = "\n".join(comments)

    # ── STEP 2: Extract tracks via GPT ──
    st.info("Step 2: Extracting track names via GPT…")
    openai.api_key = api_key

    prompt = (
        "Extract any track names and artists mentioned, and return them as a JSON list of objects "
        "with keys 'artist' and 'track'. Be flexible with format, and include entries for lines like "
        "'Artist – Track Title'.\n\n"
        f"Comments:\n{comments_text}"
    )

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw_output = response.choices[0].message.content
    except Exception as e:
        st.error(f"Failed to extract with GPT: {e}")
        st.stop()

    st.code(raw_output, language="json")

    try:
        tracks = json.loads(raw_output)
        if not isinstance(tracks, list):
            raise ValueError("Parsed JSON is not a list")
    except Exception as e:
        st.error(f"Failed to parse GPT output: {e}")
        st.stop()

    st.success("✅ Tracks identified via GPT.")

    # ── STEP 2b: Let user pick tracks ──
    options = [
        f"{t.get('artist','Unknown Artist')} – {t.get('track','Unknown Track')}"
        for t in tracks
    ]
    selected = st.multiselect("Select tracks to download:", options, default=options)

    # ── STEP 3: Download MP3s ──
    if st.button("Download Selected MP3s"):
        os.makedirs("downloads", exist_ok=True)
        st.info("Step 3: Downloading MP3s…")
        for sel in selected:
            st.write(f"▶️ Downloading {sel}")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"downloads/{sel}.%(ext)s",
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{sel}", download=True)
                    filename = ydl.prepare_filename(info)
                st.success(f"✅ Downloaded to `{filename}`")
            except Exception as e:
                st.error(f"❌ Failed to download {sel}: {e}")
