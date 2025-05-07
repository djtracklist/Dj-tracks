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
    SORT_BY_POPULAR,
)

# ── BUNDLE FFMPEG ───────────────────────────────────────────────────────
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
    os.chmod(FF_BIN, stat.S_IXUSR | stat.S_IRUSR)
    os.chmod(FP_BIN, stat.S_IXUSR | stat.S_IRUSR)

ensure_ffmpeg()

# ── STREAMLIT UI ─────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

model_choice = st.sidebar.selectbox("OpenAI model", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.secrets["OPENAI_API_KEY"]
limit = st.sidebar.number_input("Max comments to fetch", 10, 500, 100)

video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
if st.button("Extract Tracks", key="extract_btn"):

    # ── STEP 1: Download Comments ───────────────────────────────────────
    st.info("Step 1: Downloading comments (popular first)…")
    try:
        downloader = YoutubeCommentDownloader()
        comments = [
            c.get("text", "")
            for c in downloader.get_comments_from_url(video_url, sort_by=SORT_BY_POPULAR)
        ][:limit]
        if not comments:
            raise RuntimeError("No comments retrieved.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # ── STEP 2: Extract Tracks via GPT ───────────────────────────────────
    st.info("Step 2: Extracting tracks with GPT…")
    client = OpenAI(api_key=api_key)

    system_prompt = """
You are a world-class DJ tracklist curator.
From raw YouTube comments, extract:
1) All timestamped track mentions in the format:
   MM:SS Artist - Track Title (version [label] optional)
2) Any edits or corrections like “edit:…”
Return JSON:
{
  "tracks": [ { artist, track, version, label } ],
  "corrections": [ { artist, track, version, label } ]
}
"""

    few_shot = """
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
07:20 Cormac - Sparks
10:00 edit: John Noseda - Climax (VIP Mix)

JSON:
{
  "tracks": [
    {"artist": "John Noseda", "track": "Climax", "version": "", "label": ""},
    {"artist": "Roy", "track": "Shooting Star", "version": "", "label": "1987"},
    {"artist": "Cormac", "track": "Sparks", "version": "", "label": ""}
  ],
  "corrections": [
    {"artist": "John Noseda", "track": "Climax", "version": "VIP Mix", "label": ""}
  ]
}
"""

    snippet = "\n".join(comments)
    st.text_area("Prompt sent to GPT:", snippet, height=200)

    def extract_json(raw: str):
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def ask_gpt(model_name):
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "assistant", "content": few_shot},
                {"role": "user", "content": f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks, corrections, used_model = [], [], None
    for model in [model_choice, "gpt-3.5-turbo"]:
        try:
            raw = ask_gpt(model)
            parsed = json.loads(extract_json(raw))
            if "tracks" in parsed and "corrections" in parsed:
                tracks = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model = model
                break
        except Exception:
            continue

    if used_model is None:
        st.error("❌ GPT failed to extract tracks.")
        st.stop()

    all_entries = tracks + corrections
    st.session_state["dj_tracks"] = all_entries
    st.success(f"✅ Found {len(tracks)} tracks + {len(corrections)} corrections via {used_model}.")

# ── STEP 3: Display Results ───────────────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]
    st.write("### Tracks identified:")
    for i, t in enumerate(entries, start=1):
        s = f"{i}. {t['artist']} – {t['track']}"
        if t.get("version"):
            s += f" ({t['version']})"
        if t.get("label"):
            s += f" [{t['label']}]"
        st.write(s)

    # ── STEP 4: YouTube Previews & Download ─────────────────────────────
    st.write("---")
    st.write("### Select matching YouTube result to download")

    @st.cache_data(show_spinner=False)
    def fetch_youtube(entries):
        ydl = yt_dlp.YoutubeDL({"quiet": True, "skip_download": True})
        results = []
        for e in entries:
            try:
                query = f"{e['artist']} - {e['track']}"
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                results.append(info["entries"][0])
            except Exception:
                results.append(None)
        return results

    yt_results = fetch_youtube(entries)
    selected = []
    for idx, video in enumerate(yt_results):
        track = entries[idx]
        label = f"{track['artist']} – {track['track']}"
        if video is None:
            st.error(f"No video found for {label}")
            continue
        cols = st.columns([1, 4, 1])
        cols[0].image(video.get("thumbnail", ""), width=100)
        cols[1].markdown(f"**[{video.get('title')}]({video.get('webpage_url')})**")
        cols[1].caption(f"`{label}`")
        if cols[2].checkbox("", key=f"yt_{idx}"):
            selected.append(video)

    if selected and st.button("Download Selected MP3s"):
        st.info("📥 Starting download…")
        saved = []
        for video in selected:
            title = video["title"]
            url = video["webpage_url"]
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
                    mp3_path = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                    saved.append(mp3_path)
                    st.success(f"✅ {os.path.basename(mp3_path)}")
            except Exception as e:
                st.error(f"❌ Failed: {e}")

        for i, mp3 in enumerate(saved):
            if os.path.exists(mp3):
                with open(mp3, "rb") as f:
                    st.download_button(
                        label=f"Save {os.path.basename(mp3)}",
                        data=f,
                        file_name=os.path.basename(mp3),
                        mime="audio/mpeg",
                        key=f"save_{i}",
                    )
            else:
                st.warning(f"File missing: {mp3}")
