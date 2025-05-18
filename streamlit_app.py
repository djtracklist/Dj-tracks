import os import requests import tarfile import stat import io import zipfile import json import re

import streamlit as st import yt_dlp from openai import OpenAI from youtube_comment_downloader.downloader import ( YoutubeCommentDownloader, SORT_BY_POPULAR, )

── BUNDLE IN FFmpeg AT RUNTIME ─────────────────────────────────────────────────

FF_DIR = "ffmpeg-static" FF_BIN = os.path.join(FF_DIR, "ffmpeg") FP_BIN = os.path.join(FF_DIR, "ffprobe")

def ensure_ffmpeg(): if os.path.isfile(FF_BIN) and os.path.isfile(FP_BIN): return

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

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered") st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

── CONFIG ────────────────────────────────────────────────────────────────────────

api_key = st.secrets.get("OPENAI_API_KEY", "") COMMENT_LIMIT = 100 SORT_FLAG = SORT_BY_POPULAR MODELS = ["gpt-4", "gpt-3.5-turbo"]

video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...") if st.button("Extract Tracks"): if not api_key: st.error("OpenAI API key is missing from your secrets!"); st.stop() if not video_url.strip(): st.error("Please enter a YouTube URL."); st.stop()

# Step 1: reviewing comments…
st.info("Step 1: reviewing comments…")
try:
    downloader = YoutubeCommentDownloader()
    raw_comments = downloader.get_comments_from_url(video_url, sort_by=SORT_FLAG)
    comments = [c.get("text", "") for c in raw_comments][:COMMENT_LIMIT]
    if not comments:
        raise RuntimeError("No comments found.")
    st.success(f"✅ {len(comments)} comments downloaded.")
except Exception as e:
    st.error(f"Failed to download comments: {e}"); st.stop()

# Step 2: extracting Track IDs…
st.info("Step 2: extracting Track IDs…")
client = OpenAI(api_key=api_key)

system_prompt = """

You are a world-class DJ-set tracklist curator with a complete music knowledge base. Given raw YouTube comment texts, do two things:

1. Extract all timestamped track mentions in the form: MM:SS Artist - Track Title (optional remix/version and [label])


2. Extract any correction/update comments where a user writes "edit:", "correction:", "update:", "oops:", etc., clarifying a previous track.



Return ONLY a JSON object with keys "tracks" and "corrections", each a list of objects with fields: artist  (string) track   (string) version (string or empty) label   (string or empty) No extra keys or commentary. """ few_shot = """

Example Input:

Comments: 03:45 John Noseda - Climax 05:10 Roy - Shooting Star [1987] 07:20 Cormac - Sparks 10:00 edit: John Noseda - Climax (VIP Mix)

Example JSON Output:

{ "tracks": [ {"artist":"John Noseda","track":"Climax","version":"","label":""}, {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"}, {"artist":"Cormac","track":"Sparks","version":"","label":""} ], "corrections": [ {"artist":"John Noseda","track":"Climax","version":"VIP Mix","label":""} ] } """ snippet = "\n".join(comments[:100])

def extract_json(raw: str) -> str:
    m = re.search(r'\{[\s\S]*\}', raw)
    return m.group(0) if m else raw.strip()

def ask(model_name: str) -> str:
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
for m in MODELS:
    try:
        raw    = ask(m)
        clean  = extract_json(raw)
        parsed = json.loads(clean)
        if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
            tracks      = parsed["tracks"]
            corrections = parsed["corrections"]
            used_model  = m
            break
    except Exception:
        continue

if used_model is None:
    st.error("❌ GPT failed to extract any tracks or corrections."); st.stop()

all_entries = tracks + corrections
st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections.")
st.session_state["dj_tracks"] = all_entries

── STEP 3 & 4: SHOW LIST, PREVIEW & DOWNLOAD ─────────────────────────────────

if "dj_tracks" in st.session_state: all_entries = st.session_state["dj_tracks"]

st.write("### Tracks identified:")
for i, e in enumerate(all_entries, start=1):
    st.write(f"{i}. {e['artist']} – {e['track']}")

st.write("---")
st.write("### Preview YouTube results (select checkbox to download)")

@st.cache_data(show_spinner=False)
def fetch_video_candidates(entries):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }
    vids = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for e in entries:
            query = f"{e['artist']} - {e['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                video = info["entries"][0]
                vid_id    = video.get("id") or video.get("url")
                thumbnail = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                vids.append({
                    "id":           vid_id,
                    "title":        video.get("title"),
                    "webpage_url":  f"https://www.youtube.com/watch?v={vid_id}",
