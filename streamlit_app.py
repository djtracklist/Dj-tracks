import os
import requests
import tarfile
import stat
import io
import zipfile
import json

import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

# ── BUNDLE IN FFmpeg AT RUNTIME ────────────────────────────────────────────────
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

# Kick it off before any yt_dlp calls
ensure_ffmpeg()

# ── STREAMLIT UI ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.sidebar.text_input("OpenAI API Key:", type="password")
limit        = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option  = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])

# ── MAIN INPUT & EXTRACTION ───────────────────────────────────────────────────
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
if st.button("Extract Tracks"):
    if not api_key:
        st.error("Please enter your OpenAI API key.")
        st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()

    # Download comments
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=sort_flag)
        comments = [c.get("text","") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # GPT extraction
    st.info("Step 2: Extracting tracks via GPT…")
    openai.api_key = api_key

    system_prompt = """
You are a world‑class DJ‑set tracklist curator with a complete music knowledge base.
Given raw YouTube comment texts, do two things:
1) Extract all timestamped track mentions in the form:
   MM:SS Artist - Track Title (optional remix/version and [label])
2) Extract any correction/update comments where a user writes "edit:", "correction:", "update:", "oops:", etc., clarifying a previous track.

Return ONLY a JSON object with keys "tracks" and "corrections", each a list of objects with fields:
  artist  (string)
  track   (string)
  version (string or empty)
  label   (string or empty)
No extra keys or commentary.
"""
    few_shot = """
### Example Input:
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
07:20 Cormac - Sparks
10:00 edit: John Noseda - Climax (VIP Mix)

### Example JSON Output:
{
  "tracks": [
    {"artist":"John Noseda","track":"Climax","version":"","label":""},
    {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"},
    {"artist":"Cormac","track":"Sparks","version":"","label":""}
  ],
  "corrections": [
    {"artist":"John Noseda","track":"Climax","version":"VIP Mix","label":""}
  ]
}
"""
    snippet = "\n".join(comments[:100])
    st.text_area("❯ Prompt sent to GPT:", snippet, height=200)

    def extract_json(raw: str) -> str:
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def ask(model_name: str) -> dict:
        resp = openai.ChatCompletion.create(
            model=model_name,
            messages=[
                {"role":"system","content":system_prompt},
                {"role":"assistant","content":few_shot},
                {"role":"user","content":f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks, corrections, used_model = [], [], None
    for m in (model_choice, "gpt-3.5-turbo"):
        try:
            raw    = ask(m)
            clean  = extract_json(raw)
            parsed = json.loads(clean)
            if "tracks" in parsed and "corrections" in parsed:
                tracks      = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model  = m
                break
        except Exception:
            continue

    if not used_model:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    all_entries = tracks + corrections
    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections via {used_model}.")
    st.session_state["dj_tracks"] = all_entries

# ── STEP 3 & 4: SHOW LIST, PREVIEW & DOWNLOAD ──────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]

    st.write("### Tracks identified:")
    for i, e in enumerate(entries, 1):
        st.write(f"{i}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview & select YouTube results")

    @st.cache_data
    def fetch_video_candidates(entries):
        ydl = yt_dlp.YoutubeDL({"quiet": True, "skip_download": True})
        vids = []
        for e in entries:
            query = f"{e['artist']} - {e['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                vids.append(info["entries"][0])
            except Exception:
                vids.append(None)
        return vids

    candidates = fetch_video_candidates(entries)
    to_download = []
    for idx, vid in enumerate(candidates):
        e = entries[idx]
        label = f"{e['artist']} – {e['track']}"
        if not vid:
            st.error(f"No match for **{label}**")
            continue

        c1, c2, c3 = st.columns([1, 4, 1])
        thumb = vid.get("thumbnail")
        if thumb:
            c1.image(thumb, width=100)
        else:
            c1.write("❓")

        title = vid.get("title","Unknown")
        url   = vid.get("webpage_url","#")
        c2.markdown(f"**[{title}]({url})**")
        c2.caption(f"Search: `{label}`")

        if c3.checkbox("", key=f"dl_{idx}"):
            to_download.append(vid)

    st.write("---")
    if to_download and st.button("Download Selected MP3s"):
        st.info("📥 Downloading…")
        os.makedirs("downloads", exist_ok=True)
        saved = []

        for vid in to_download:
            t = vid["title"]
            u = vid["webpage_url"]
            st.write(f"▶️ {t}")
            opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads","%(title)s.%(ext)s"),
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
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(u, download=True)
                    fn   = ydl.prepare_filename(info)
                    mp3  = os.path.splitext(fn)[0] + ".mp3"
                    saved.append(mp3)
                st.success(f"✅ {os.path.basename(mp3)}")
            except Exception as e:
                st.error(f"❌ Failed {t}: {e}")

        # bundle zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for p in saved:
                if os.path.exists(p):
                    buf_path = os.path.basename(p)
                    z.write(p, arcname=buf_path)
        buf.seek(0)

        if saved:
            st.download_button("Download All as ZIP", data=buf,
                               file_name="dj_tracks.zip", mime="application/zip")
        else:
            st.warning("No files downloaded.")
    elif not to_download:
        st.info("Select at least one video above to enable downloading.")
