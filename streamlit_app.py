import os
import requests
import tarfile
import stat
import json
import re

import streamlit as st
import yt_dlp
from openai import OpenAI
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

# ── BUNDLE IN FFmpeg AT RUNTIME ─────────────────────────────────────────────────
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

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# ── CONFIGURATION ──────────────────────────────────────────────────────────────
api_key      = st.secrets.get("OPENAI_API_KEY", "")
COMMENT_LIMIT = 100
SORT_FLAG     = SORT_BY_POPULAR
MODELS        = ["gpt-4", "gpt-3.5-turbo"]

# ── UTIL: Fetch YouTube search results ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_video_candidates(entries):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "http_headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        "geo_bypass": True,
        "nocheckcertificate": True,
    }
    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for e in entries:
            query = f"{e['artist']} - {e['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                vid = info.get("entries", [None])[0]
                if not vid:
                    results.append(None)
                else:
                    vid_id = vid.get("id") or vid.get("url")
                    results.append({
                        "id": vid_id,
                        "title": vid.get("title"),
                        "webpage_url": f"https://www.youtube.com/watch?v={vid_id}",
                        "thumbnail": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                    })
            except Exception:
                results.append(None)
    return results

# ── SECTION: YouTube Set Extraction ─────────────────────────────────────────────
video_url = st.text_input(
    "YouTube DJ Set URL",
    placeholder="https://www.youtube.com/watch?v=...",
    key="url_input"
)
if st.button("Extract Tracks", key="extract_setlist"):
    if not api_key:
        st.error("OpenAI API key is missing!")
        st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()

    st.info("Step 1: downloading comments…")
    try:
        downloader    = YoutubeCommentDownloader()
        raw_comments  = downloader.get_comments_from_url(video_url, sort_by=SORT_FLAG)
        comments      = [c.get("text", "") for c in raw_comments][:COMMENT_LIMIT]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    st.info("Step 2: extracting track IDs…")
    client = OpenAI(api_key=api_key)
    system_prompt = (
        "You are a world-class DJ-set tracklist curator.\n"
        "Given raw YouTube comments, extract timestamped tracks and corrections.\n"
        "Return ONLY JSON with 'tracks' and 'corrections' lists "
        "(fields: artist, track, version, label)."
    )
    few_shot = (
        "### Example Input:\nComments:\n03:45 Artist A - Song A\n"
        "05:10 Artist B - Song B [2010]\n\n"
        "### Example JSON Output:\n{ 'tracks': [...], 'corrections': [...] }"
    )
    snippet = "\n".join(comments)

    def extract_json(raw: str) -> str:
        m = re.search(r"\{[\s\S]*\}", raw)
        return m.group(0) if m else raw.strip()

    tracks, corrections = [], []
    used_model = None
    for model in MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",    "content": system_prompt},
                    {"role": "assistant", "content": few_shot},
                    {"role": "user",      "content": f"Comments:\n{snippet}"}
                ],
