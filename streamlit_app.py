import subprocess
import json
import streamlit as st
import openai
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_POPULAR,
    SORT_BY_RECENT,
)

# ————————————————————————————————————————————————————————————————————————————————
# Streamlit UI
st.title("DJ Set Track Extractor + MP3 Downloader")

video_url = st.text_input("YouTube DJ set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")
limit = st.number_input("Max comments to fetch:", min_value=10, max_value=500, value=100)
sort_option = st.selectbox("Sort comments by:", ["popular", "recent"])
download_mp3 = st.checkbox("Enable MP3 download step", value=False)

if st.button("Extract Tracks & (optionally) Download MP3s"):
    st.info("Step 1: Downloading YouTube comments…")

    # map string sort → numeric constant
    sort_code = SORT_BY_POPULAR if sort_option == "popular" else SORT_BY_RECENT

    # run CLI
    cmd = [
        "youtube-comment-downloader",
        "--url", video_url,
        "--limit", str(limit),
        "--sort", str(sort_code),
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        st.error(f"Failed to download comments: {proc.stderr.decode(errors='ignore')}")
        st.stop()

    comments = []
    for line in proc.stdout.decode("utf-8", errors="ignore").splitlines():
        try:
            obj = json.loads(line)
            comments.append(obj.get("text", ""))
        except json.JSONDecodeError:
            continue

    st.success(f"{len(comments)} comments downloaded.")

    # ————————————————————————————————————————————————————————————————————————————————
    st.info("Step 2: Extracting track names using GPT…")
    openai.api_key = api_key

    prompt = f"""You are an expert at parsing DJ‐set discussions.  
Extract any track names and artists mentioned in the following comments (ignore off‐topic chatter).  
Return your answer as a JSON array of objects with keys "artist" and "track".  
Comments:
{"".join(comments[:min(len(comments), 50)])}
"""
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = resp.choices[0].message.content
        tracks = json.loads(raw)
        if not isinstance(tracks, list):
            raise ValueError("GPT did not return a list")
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    st.success("Tracks identified!")
    # ————————————————————————————————————————————————————————————————————————————————
    # display with checkboxes
    selected = []
    st.write("Select tracks to download:")
    for idx, item in enumerate(tracks):
        label = f"{item.get('artist','?')} — {item.get('track','?')}"
        if st.checkbox(label, value=True, key=idx):
            selected.append(label)

    # ————————————————————————————————————————————————————————————————————————————————
    if download_mp3 and st.button("Download Selected MP3s"):
        st.info("Step 3: Downloading MP3s…")
        for sel in selected:
            # simple yt-dlp search/download call
            cmd = [
                "yt-dlp",
                f"ytsearch1:{sel}",
                "-x", "--audio-format", "mp3",
            ]
            subprocess.run(cmd)
        st.success("All done!")

