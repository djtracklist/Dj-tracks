import os
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# --- App setup ---
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# --- Inputs ---
video_url = st.text_input(
    "Enter YouTube DJ Set URL",
    placeholder="https://www.youtube.com/watch?v=..."
)
model = st.selectbox(
    "Choose OpenAI model",
    ["gpt-4", "gpt-3.5-turbo"]
)
api_key = st.text_input(
    "Enter your OpenAI API Key",
    type="password"
)

# ensure download folder exists
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Main action ---
if st.button("Extract Tracks & Download MP3s"):
    # Validate
    if not video_url or not api_key:
        st.error("⚠️ Please provide both the YouTube URL and your OpenAI API key.")
        st.stop()

    ### Step 1: Fetch comments ###
    st.info("Step 1: Downloading YouTube comments...")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(
            video_url,
            sort_by=SORT_BY_RECENT
        ):
            comments.append(c.get("text", ""))
            if len(comments) >= 100:
                break
        if not comments:
            raise ValueError("No comments were returned.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    ### Step 2: Extract tracklist via GPT ###
    st.info("Step 2: Extracting track names using GPT...")
    openai.api_key = api_key
    snippet = "\n".join(comments[:50])
    prompt = (
        "Extract any track names and artists mentioned in the text below, "
        "and return them as a JSON array of objects with fields 'artist' and 'track'.\n\n"
        "Comments:\n" + snippet
    )
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt.strip()}],
            temperature=0
        )
        raw_output = resp.choices[0].message.content.strip()
        st.code(raw_output, language="json")
        tracks = json.loads(raw_output)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("The parsed JSON was empty or not a list.")
        st.success(f"✅ {len(tracks)} tracks identified.")
    except Exception as e:
        st.error(f"GPT step failed or returned invalid JSON: {e}")
        st.stop()

    ### Step 3: Display and select ###
    st.write("---")
    st.write("### Select tracks to download")
    selected = []
    for idx, t in enumerate(tracks):
        artist = t.get("artist", "").strip() or "Unknown Artist"
        track  = t.get("track", "").strip()  or "Unknown Track"
        label  = f"{artist} — {track}"
        if st.checkbox(label, key=idx, value=True):
            selected.append(label)

    ### Step 4: Download selected ###
    if selected:
        if st.button("Download Selected as MP3"):
            st.info("Step 4: Downloading selected tracks…")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
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
                    st.write(f"▶️ Downloading: {q}")
                    try:
                        ydl.download([f"ytsearch1:{q}"])
                        st.write("✅ Done")
                    except Exception as e:
                        st.error(f"Failed: {q} ({e})")
            st.success(
                f"🎉 All selected tracks downloaded to the “{DOWNLOAD_DIR}/” folder."
            )
    else:
        st.info("No tracks selected. Check the boxes above to enable download.")
