import os
import io
import json
import zipfile
import requests
import tarfile
import stat

import streamlit as st
import yt_dlp
from openai import OpenAI
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

# ── SETUP FFMPEG ────────────────────────────────────────────────────────────────
FF_DIR = "ffmpeg-static"
FF_BIN = os.path.join(FF_DIR, "ffmpeg")
FP_BIN = os.path.join(FF_DIR, "ffprobe")

def ensure_ffmpeg():
    if os.path.isfile(FF_BIN) and os.path.isfile(FP_BIN):
        return
    os.makedirs(FF_DIR, exist_ok=True)
    url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    local_tar = os.path.join(FF_DIR, "ffmpeg.tar.xz")

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_tar, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    with tarfile.open(local_tar, mode="r:xz") as tar:
        for member in tar.getmembers():
            name = os.path.basename(member.name)
            if name in ("ffmpeg", "ffprobe"):
                member.name = name
                tar.extract(member, FF_DIR)

    os.remove(local_tar)
    os.chmod(FF_BIN, stat.S_IRUSR | stat.S_IXUSR)
    os.chmod(FP_BIN, stat.S_IRUSR | stat.S_IXUSR)

ensure_ffmpeg()

# ── UI CONFIG ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
limit = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])
api_key = st.secrets.get("OPENAI_API_KEY", "")

video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")

# ── MAIN ────────────────────────────────────────────────────────────────────────
if st.button("Extract Tracks", key="extract_btn"):
    if not api_key:
        st.error("Missing OpenAI API key in secrets.toml")
        st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()

    # Step 1: Download comments
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=sort_flag)
        comments = [c.get("text", "") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: GPT track extraction
    st.info("Step 2: Extracting tracks via GPT…")
    client = OpenAI(api_key=api_key)

    system_prompt = """
You are a DJ set tracklist expert. Given raw YouTube comment text, do two things:
1) Extract timestamped track mentions in the form MM:SS Artist - Track Title (with optional version or label).
2) Extract corrections that include “edit:”, “correction:”, “update:” etc.

Return JSON:
{
  "tracks": [ { "artist": "", "track": "", "version": "", "label": "" }, ... ],
  "corrections": [ { "artist": "", "track": "", "version": "", "label": "" }, ... ]
}
"""

    few_shot = """
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
07:20 Cormac - Sparks
10:00 edit: John Noseda - Climax (VIP Mix)
"""

    def ask_gpt(model_name: str, text: str) -> dict:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "assistant", "content": few_shot},
                {"role": "user", "content": f"Comments:\n{text}"},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content
        if content.startswith("```"):
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1].strip()
        return json.loads(content)

    result = None
    for model in [model_choice, "gpt-3.5-turbo"]:
        try:
            result = ask_gpt(model, "\n".join(comments))
            if "tracks" in result and "corrections" in result:
                break
        except Exception:
            continue

    if not result:
        st.error("GPT failed to extract tracks.")
        st.stop()

    tracks = result["tracks"] + result["corrections"]
    st.session_state["tracks"] = tracks
    st.success(f"✅ {len(tracks)} tracks identified.")

# ── SELECTION & DOWNLOAD ────────────────────────────────────────────────────────
if "tracks" in st.session_state:
    tracks = st.session_state["tracks"]
    st.write("### Tracks identified:")
    for i, t in enumerate(tracks, start=1):
        label = f"{t['artist']} - {t['track']}"
        if t.get("version"): label += f" ({t['version']})"
        if t.get("label"):   label += f" [{t['label']}]"
        st.write(f"{i}. {label}")

    @st.cache_data(show_spinner=False)
    def fetch_youtube_matches(tracks):
        ydl = yt_dlp.YoutubeDL({"quiet": True, "skip_download": True})
        videos = []
        for t in tracks:
            query = f"{t['artist']} - {t['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                videos.append(info["entries"][0])
            except Exception:
                videos.append(None)
        return videos

    st.write("---")
    st.write("### Preview YouTube matches and select")

    matched_videos = fetch_youtube_matches(tracks)
    selections = []

    for i, video in enumerate(matched_videos):
        t = tracks[i]
        label = f"{t['artist']} – {t['track']}"
        if not video:
            st.error(f"No match for {label}")
            continue

        cols = st.columns([1, 4, 1])
        cols[0].image(video["thumbnail"], width=100)
        cols[1].markdown(f"**[{video['title']}]({video['webpage_url']})**")
        cols[1].caption(f"Search: {label}")
        if cols[2].checkbox("", key=f"check_{i}"):
            selections.append(video)

    st.write("---")
    if selections:
        st.info("📥 Downloading selected tracks…")
        for i, vid in enumerate(selections):
            title = vid["title"]
            url = vid["webpage_url"]
            st.write(f"▶️ {title}")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet": True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    path = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                    with open(path, "rb") as f:
                        st.download_button(
                            label=f"💾 Save {os.path.basename(path)}",
                            data=f.read(),
                            file_name=os.path.basename(path),
                            mime="audio/mpeg",
                            key=f"mp3_{i}",
                        )
            except Exception as e:
                st.error(f"❌ Download failed: {e}")
    else:
        st.info("Select at least one video to download.")
