# streamlit_app.py

import os
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

# ─── CONFIG ───────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY")
if not OPENAI_KEY:
    st.error("❌ Missing OpenAI API key in .streamlit/secrets.toml")
    st.stop()
openai.api_key = OPENAI_KEY  # set your key for the new SDK

# ─── SIDEBAR ──────────────────────────────────────────────────────────
model_choice = st.sidebar.selectbox(
    "Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"], key="mdl"
)
limit = st.sidebar.number_input(
    "Max comments to fetch:", min_value=10, max_value=500, value=100, key="lim"
)
sort_option = st.sidebar.selectbox(
    "Sort comments by:", ["recent", "popular"], key="srt"
)

# ─── MAIN INPUT ───────────────────────────────────────────────────────
st.title("🎧 DJ Set Tracklist & MP3 Downloader")
video_url = st.text_input(
    "YouTube DJ Set URL",
    placeholder="https://www.youtube.com/watch?v=...",
    key="url"
)

if st.button("Extract Tracks", key="btn_extract"):
    if not video_url.strip():
        st.error("❌ Please enter a YouTube URL")
        st.stop()

    # 1) Download comments
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(
            video_url, sort_by=sort_flag
        )
        comments = [c.get("text", "") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ Downloaded {len(comments)} comments.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 2) GPT extraction
    st.info("Step 2: Extracting tracklist via GPT…")
    SYSTEM_PROMPT = """
You are a world‑class DJ‑set tracklist curator with exhaustive music knowledge.
Given raw YouTube comment text, do two things:
1) Extract timestamped track mentions in the form:
   MM:SS Artist - Title (optional remix/version) [label]
2) Extract any corrections (lines starting with "edit:", "correction:", etc.) as separate entries.

Return only a JSON object with exactly two keys:
{
  "tracks":    [ {artist, track, version, label}, … ],
  "corrections":[ {artist, track, version, label}, … ]
}
No extra keys or commentary.
"""
    FEW_SHOT = """
### Example Input:
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
10:00 edit: John Noseda - Climax (VIP Mix)

### Example JSON Output:
{
  "tracks":[
    {"artist":"John Noseda","track":"Climax","version":"","label":""},
    {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"}
  ],
  "corrections":[
    {"artist":"John Noseda","track":"Climax","version":"VIP Mix","label":""}
  ]
}
"""

    snippet = "\n".join(comments[:100])
    st.text_area("❯ Prompt sent to GPT (first 100 comments):", snippet, height=200, key="prompt")

    def extract_json(raw: str) -> str:
        txt = raw.strip()
        if txt.startswith("```"):
            parts = txt.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return txt

    def ask(model: str) -> str:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "assistant", "content": FEW_SHOT},
                {"role": "user",      "content": f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks, corrections, used_model = [], [], None
    for m in (model_choice, "gpt-3.5-turbo"):
        try:
            raw = ask(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks, corrections, used_model = parsed["tracks"], parsed["corrections"], m
                break
        except Exception:
            continue

    if not used_model:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    st.success(f"✅ Extracted {len(tracks)} tracks + {len(corrections)} corrections via {used_model}")
    st.session_state["dj_tracks"] = tracks + corrections

# ─── PREVIEW & DOWNLOAD ─────────────────────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]

    st.write("### Tracks identified:")
    for i, e in enumerate(entries, start=1):
        st.write(f"{i}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview & select YouTube videos")

    @st.cache_data(show_spinner=False)
    def fetch_videos(es):
        ydl = yt_dlp.YoutubeDL({"quiet": True, "skip_download": True})
        vids = []
        for ent in es:
            q = f"{ent['artist']} - {ent['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{q}", download=False)
                vids.append(info["entries"][0])
            except Exception:
                vids.append(None)
        return vids

    video_results = fetch_videos(entries)
    to_download = []

    for idx, video in enumerate(video_results):
        ent = entries[idx]
        label = f"{ent['artist']} – {ent['track']}"
        if video is None:
            st.error(f"No YouTube match for **{label}**", key=f"err_{idx}")
            continue

        c1, c2, c3 = st.columns([1, 4, 1])
        thumb = video.get("thumbnail")
        if thumb:
            c1.image(thumb, width=100, key=f"img_{idx}")
        else:
            c1.write("❓", key=f"imgx_{idx}")

        title = video.get("title", "Unknown title")
        url   = video.get("webpage_url", "#")
        c2.markdown(f"**[{title}]({url})**", key=f"md_{idx}")
        c2.caption(f"Search: `{label}`", key=f"cap_{idx}")

        if c3.checkbox("Select", key=f"chk_{idx}", label_visibility="collapsed"):
            to_download.append(video)

    st.write("---")
    if to_download and st.button("Download Selected MP3s", key="btn_dl"):
        st.info("📥 Downloading selected tracks…")
        os.makedirs("downloads", exist_ok=True)

        # optional cookies.txt for age‑restricted videos
        cookies_file = None
        up = st.file_uploader("Upload cookies.txt (optional)", type="txt", key="upload")
        if up:
            cookies_file = os.path.join("downloads", "cookies.txt")
            with open(cookies_file, "wb") as f:
                f.write(up.getbuffer())

        saved = []
        for vid in to_download:
            t = vid["title"]
            u = vid["webpage_url"]
            st.write(f"▶️ {t}", key=f"log_{t}")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
            }
            if cookies_file:
                ydl_opts["cookiefile"] = cookies_file

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(u, download=True)
            except yt_dlp.utils.DownloadError as de:
                msg = str(de)
                if "Sign in to confirm your age" in msg:
                    st.error("⚠️ Age‑restricted video; please provide cookies.txt", key=f"age_{t}")
                else:
                    st.error(f"❌ Failed to download {t}: {de}", key=f"dlerr_{t}")
                continue

            fn = ydl.prepare_filename(info)
            mp3 = os.path.splitext(fn)[0] + ".mp3"
            saved.append(mp3)
            st.success(f"✅ {os.path.basename(mp3)}", key=f"succ_{t}")

        st.write("### Save MP3s")
        for i, path in enumerate(saved):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    st.download_button(
                        label=f"Save {os.path.basename(path)}",
                        data=f,
                        file_name=os.path.basename(path),
                        mime="audio/mpeg",
                        key=f"save_{i}"
                    )
            else:
                st.warning(f"Missing file: {path}", key=f"warn_{i}")
    elif not to_download:
        st.info("Select at least one video above to enable downloading.", key="info_no_vid")
