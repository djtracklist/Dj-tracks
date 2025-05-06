# streamlit_app.py

import os
import io
import zipfile
import json

import streamlit as st
import yt_dlp
import ffmpeg_static
from openai import OpenAI
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

# ─── CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
FFMPEG_BIN = ffmpeg_static.path
FFPROBE_BIN = FFMPEG_BIN.replace("ffmpeg", "ffprobe")

# ─── SIDEBAR ──────────────────────────────────────────────────────────────
model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.sidebar.text_input("OpenAI API Key:", type="password")
limit        = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option  = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])

# ─── TITLE & INPUT ────────────────────────────────────────────────────────
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Extract Tracks", key="extract_btn"):
    # — Validation —
    if not api_key:
        st.error("Please enter your OpenAI API key."); st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL."); st.stop()

    # — Step 1: Download comments —
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

    # — Step 2: GPT extraction (your tried‑and‑true snippet) —
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
        if raw.strip().startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
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

# ─── STEP 3 & 4: PREVIEW & DOWNLOAD ───────────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]

    # 1) Static list
    st.write("### Tracks identified:")
    for i, e in enumerate(entries, 1):
        st.write(f"{i}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview & select YouTube videos")

    @st.cache_data(show_spinner=False)
    def fetch_video_candidates(es):
        ydl = yt_dlp.YoutubeDL({"quiet": True, "skip_download": True})
        vids = []
        for ent in es:
            query = f"{ent['artist']} - {ent['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                vids.append(info["entries"][0])
            except Exception:
                vids.append(None)
        return vids

    video_results = fetch_video_candidates(entries)
    to_download = []

    for idx, video in enumerate(video_results):
        ent   = entries[idx]
        label = f"{ent['artist']} – {ent['track']}"
        if video is None:
            st.error(f"No YouTube match for **{label}**")
            continue

        c1, c2, c3 = st.columns([1, 4, 1])
        thumb = video.get("thumbnail")
        if thumb:
            c1.image(thumb, width=100)
        else:
            c1.write("❓")

        title = video.get("title", "Unknown title")
        url   = video.get("webpage_url", "#")
        c2.markdown(f"**[{title}]({url})**")
        c2.caption(f"Search: `{label}`")

        # give each checkbox a non‑empty label but hide it
        if c3.checkbox(f"select_{idx}", label_visibility="collapsed"):
            to_download.append(video)

    st.write("---")
    if to_download and st.button("Download Selected MP3s"):
        st.info("📥 Downloading selected tracks…")
        os.makedirs("downloads", exist_ok=True)

        # optional cookies for age‑restricted videos
        cookies = None
        up = st.file_uploader("Upload cookies.txt (optional)", type="txt")
        if up:
            cookies = os.path.join("downloads", "cookies.txt")
            with open(cookies, "wb") as f:
                f.write(up.getbuffer())

        saved = []
        for vid in to_download:
            title = vid["title"]
            url   = vid["webpage_url"]
            st.write(f"▶️ {title}")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "ffmpeg_location": FFMPEG_BIN,
                "ffprobe_location": FFPROBE_BIN,
                "quiet": True,
            }
            if cookies:
                ydl_opts["cookiefile"] = cookies

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    orig = ydl.prepare_filename(info)
                    mp3  = os.path.splitext(orig)[0] + ".mp3"
                    saved.append(mp3)
                st.success(f"✅ {os.path.basename(mp3)}")
            except yt_dlp.utils.DownloadError as de:
                msg = str(de)
                if "Sign in to confirm your age" in msg:
                    st.error("⚠️ Age‑restricted—please upload cookies.txt")
                else:
                    st.error(f"❌ Failed to download {title}: {de}")
                continue

        # 5) Offer individual save buttons
        st.write("### Save MP3s to your device")
        for i, path in enumerate(saved):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    st.download_button(
                        label=f"Save {os.path.basename(path)}",
                        data=f,
                        file_name=os.path.basename(path),
                        mime="audio/mpeg",
                        key=f"save_{i}",
                    )
            else:
                st.warning(f"Missing file: {path}")
    elif not to_download:
        st.info("Select at least one video above to enable downloading.")
