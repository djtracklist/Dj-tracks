import os
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT, SORT_BY_POPULAR

# --- Page config ---
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# --- Sidebar inputs ---
model = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-3.5-turbo", "gpt-4"])
api_key = st.sidebar.text_input("OpenAI API Key:", type="password")
limit = st.sidebar.number_input("Max comments to fetch:", min_value=10, max_value=500, value=100)
sort_option = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])
download_mp3 = st.sidebar.checkbox("Enable MP3 download", value=False)

# --- Main input ---
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Extract Tracks & Download"):
    # 1) Validate inputs
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()
    if not api_key.strip():
        st.error("Please enter your OpenAI API key.")
        st.stop()

    # 2) Download comments via Python API
    st.info("Step 1: Downloading comments…")
    try:
        ycd = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        comments = []
        for c in ycd.get_comments_from_url(video_url, sort_by=sort_flag):
            text = c.get("text", "").strip()
            if text:
                comments.append(text)
            if len(comments) >= limit:
                break
        if not comments:
            raise RuntimeError("No comments returned by downloader.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 3) Extract tracklist via GPT
    st.info("Step 2: Extracting track names via GPT…")
    openai.api_key = api_key
    snippet = "\n".join(comments[:50])
    prompt = (
        "You are an expert at reading YouTube comment tracklists.\n"
        "Extract every clear 'Artist – Track' mention from the text below.\n"
        "Return only valid JSON: an array of objects with keys 'artist' and 'track'.\n\n"
        f"Comments:\n{snippet}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        st.code(raw, language="json")
        tracks = json.loads(raw)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("GPT returned empty or invalid list.")
        st.success(f"✅ {len(tracks)} tracks identified.")
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    # 4) Display track options
    st.write("---")
    st.write("### Select tracks to download")
    labels = [f"{t.get('artist','Unknown Artist')} — {t.get('track','Unknown Track')}" for t in tracks]
    selected = st.multiselect("Choose from the extracted tracks:", options=labels, default=labels)

    # 5) Download MP3s if enabled
    if download_mp3 and selected:
        st.info("Step 3: Downloading MP3s…")
        os.makedirs("downloads", exist_ok=True)
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for q in selected:
                st.write(f"▶️ {q}")
                try:
                    ydl.download([f"ytsearch1:{q}"])
                    st.write("Done")
                except Exception as e:
                    st.error(f"Failed to download {q}: {e}")
        st.success("🎉 All selected tracks downloaded to 'downloads/' folder.")
    elif download_mp3:
        st.warning("No tracks selected for download.")
