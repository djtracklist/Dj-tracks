import os
import requests
import tarfile
import stat
import io
import zipfile
import json

import streamlit as st
import yt_dlp
from openai import OpenAI
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

# ── BUNDLE IN FFmpeg AT RUNTIME ─────────────────────────────────────────────────
FF_DIR = "ffmpeg-static"
FF_BIN = os.path.join(FF_DIR, "ffmpeg")
FP_BIN = os.path.join(FF_DIR, "ffprobe")

def ensure_ffmpeg():
    if os.path.isfile(FF_BIN) and os.path.isfile(FP_BIN):
        return  # already in place

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
                member.name = name  # strip leading folders
                tar.extract(member, FF_DIR)

    os.remove(local_tar)
    os.chmod(FF_BIN, stat.S_IXUSR | stat.S_IRUSR)
    os.chmod(FP_BIN, stat.S_IXUSR | stat.S_IRUSR)

# Make sure the binaries are present before any yt_dlp usage
ensure_ffmpeg()

# ── APP UI & LOGIC ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# ── SIDEBAR ───────────────────────────────────────────────────────────────────────
model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.secrets["OPENAI_API_KEY"]
limit        = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option  = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])

# ── MAIN INPUT & EXTRACTION ───────────────────────────────────────────────────────
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
if st.button("Extract Tracks", key="extract_btn"):
    if not api_key:
        st.error("OpenAI API key is missing from secrets!"); st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL."); st.stop()

    # Step 1: Download comments
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option=="recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=sort_flag)
        comments = [c.get("text","") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}"); st.stop()

    # Step 2: GPT extraction
    st.info("Step 2: Extracting tracks via GPT…")
    client = OpenAI(api_key=api_key)
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
            if len(parts)>=3:
                return parts[1].strip()
        return raw.strip()

    def ask(model_name: str) -> str:
        resp = client.chat.completions.create(
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
    for m in [model_choice, "gpt-3.5-turbo"]:
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
    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections via {used_model}.")
    st.session_state["dj_tracks"] = all_entries

# ── STEP 3 & 4: SHOW LIST, PREVIEW & DOWNLOAD ─────────────────────────────────
if "dj_tracks" in st.session_state:
    all_entries = st.session_state["dj_tracks"]

    # 1) Static list of tracks
    st.write("### Tracks identified:")
    for i, e in enumerate(all_entries, start=1):
        st.write(f"{i}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview YouTube results (select to download)")

    @st.cache_data(show_spinner=False)
    def fetch_video_candidates(entries):
        ydl = yt_dlp.YoutubeDL({"quiet":True,"skip_download":True})
        vids=[]
        for e in entries:
            query = f"{e['artist']} - {e['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                vids.append(info["entries"][0])
            except Exception:
                vids.append(None)
        return vids

    video_results = fetch_video_candidates(all_entries)

    to_download=[]
    for idx, video in enumerate(video_results):
        entry = all_entries[idx]
        label = f"{entry['artist']} – {entry['track']}"
        if video is None:
            st.error(f"No YouTube match for **{label}**")
            continue

        cols = st.columns([1,4,1])
        thumb = video.get("thumbnail")
        if thumb:
            cols[0].image(thumb,width=100)
        else:
            cols[0].write("❓")

        title = video.get("title","Unknown title")
        url   = video.get("webpage_url","#")
        cols[1].markdown(f"**[{title}]({url})**")
        cols[1].caption(f"Search: `{entry['artist']} - {entry['track']}`")

        if cols[2].checkbox("",key=f"vid_{idx}"):
            to_download.append(video)

    st.write("---")
    if to_download and st.button("Download Selected MP3s",key="dl_btn"):
        st.info("📥 Downloading selected tracks…")
        os.makedirs("downloads",exist_ok=True)
        saved=[]

        for video in to_download:
            title = video.get("title")
            url   = video.get("webpage_url")
            st.write(f"▶️ {title}")
            ydl_opts = {
                "format":"bestaudio/best",
                "outtmpl": os.path.join("downloads","%(title)s.%(ext)s"),
                "postprocessors":[{
                    "key":"FFmpegExtractAudio",
                    "preferredcodec":"mp3",
                    "preferredquality":"192",
                }],
                # ← finally ensure yt_dlp can find _both_ binaries:
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet":True,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    orig = ydl.prepare_filename(info)
                    mp3  = os.path.splitext(orig)[0] + ".mp3"
                    saved.append(mp3)
                st.success(f"✅ {os.path.basename(mp3)}")
            except Exception as e:
                st.error(f"❌ Failed to download {title}: {e}")

        st.write("### Save MP3s to your device")
        for i, mp3_path in enumerate(saved):
            if os.path.exists(mp3_path):
                with open(mp3_path,"rb") as f:
                    st.download_button(
                        label=f"Save {os.path.basename(mp3_path)}",
                        data=f,
                        file_name=os.path.basename(mp3_path),
                        mime="audio/mpeg",
                        key=f"dl_{i}",
                    )
            else:
                st.warning(f"File missing: {mp3_path}")
    elif not to_download:
        st.info("Select at least one video above to enable downloading.")
