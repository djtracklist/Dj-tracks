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

# ─── CONFIG ───────────────────────────────────────────────────────────
st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
FF_BIN = ffmpeg_static.path
FP_BIN = FF_BIN.replace("ffmpeg", "ffprobe")

# ─── SIDEBAR ──────────────────────────────────────────────────────────
model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.secrets["OPENAI_API_KEY"]
limit        = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option  = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])

# ─── MAIN INPUT ───────────────────────────────────────────────────────
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Extract Tracks"):
    # 1) VALIDATION
    if not api_key:
        st.error("❌ Missing OpenAI key in secrets.toml"); st.stop()
    if not video_url.strip():
        st.error("❌ Please enter a YouTube URL"); st.stop()

    # 2) SCRAPE COMMENTS
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=sort_flag)
        comments = [c.get("text","") for c in raw_comments][:limit]
        if not comments:
            raise RuntimeError("No comments returned.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 3) EXTRACT TRACKS VIA GPT
    st.info("Step 2: Extracting tracklist via GPT…")
    client = OpenAI(api_key=api_key)
    system_prompt = """
You are a world‑class DJ‑set tracklist curator. Given raw YouTube comment text, do two things:
1) Extract every timestamped track mention: “MM:SS Artist - Title (remix/version) [label]”
2) Extract any corrections that begin with “edit:”, “correction:”, etc., as separate entries.

Return _only_ a JSON object:
{
  "tracks":    [ {artist, track, version, label}, … ],
  "corrections":[ {artist, track, version, label}, … ]
}
No extra keys or prose.
"""
    few_shot = """
### Input:
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
10:00 edit: John Noseda - Climax (VIP Mix)

### Output:
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
    st.text_area("❯ Prompt (first 100 comments):", snippet, height=200)

    def extract_json(raw: str) -> str:
        if raw.strip().startswith("```"):
            parts = raw.split("```")
            if len(parts)>=3:
                return parts[1].strip()
        return raw.strip()

    def ask(model: str) -> str:
        res = client.ChatCompletion.create(
            model=model,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"assistant", "content":few_shot},
                {"role":"user",      "content":f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return res.choices[0].message.content

    tracks, corrections, used = [], [], None
    for m in [model_choice, "gpt-3.5-turbo"]:
        try:
            raw    = ask(m)
            clean  = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks, corrections, used = parsed["tracks"], parsed["corrections"], m
                break
        except Exception:
            continue

    if not used:
        st.error("❌ GPT failed to parse any track data."); st.stop()

    st.success(f"✅ Extracted {len(tracks)} tracks + {len(corrections)} corrections via {used}")
    st.session_state["dj_tracks"] = tracks + corrections

# ─── PREVIEW & DOWNLOAD ─────────────────────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]

    st.write("### Tracks identified:")
    for i, e in enumerate(entries, 1):
        st.write(f"{i}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview & select YouTube videos")

    @st.cache_data(show_spinner=False)
    def search_videos(es):
        ydl = yt_dlp.YoutubeDL({"quiet":True, "skip_download":True})
        out = []
        for ent in es:
            q = f"{ent['artist']} - {ent['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{q}", download=False)
                out.append(info["entries"][0])
            except Exception:
                out.append(None)
        return out

    vids = search_videos(entries)
    to_dl = []

    for idx, video in enumerate(vids):
        ent   = entries[idx]
        label = f"{ent['artist']} – {ent['track']}"
        if not video:
            st.error(f"No match for **{label}**")
            continue

        c1, c2, c3 = st.columns([1,4,1])
        thumb = video.get("thumbnail")
        if thumb: c1.image(thumb, width=100)
        else:     c1.write("❓")

        title = video.get("title","Unknown")
        url   = video.get("webpage_url","#")
        c2.markdown(f"**[{title}]({url})**")
        c2.caption(f"Search: `{label}`")

        if c3.checkbox("Select", key=f"chk_{idx}", label_visibility="collapsed"):
            to_dl.append(video)

    st.write("---")
    if to_dl and st.button("Download Selected MP3s"):
        st.info("📥 Downloading…")
        os.makedirs("downloads", exist_ok=True)

        # optional cookies for age-restricted
        cookies = None
        up = st.file_uploader("Upload cookies.txt (optional)", type="txt")
        if up:
            cookies = os.path.join("downloads","cookies.txt")
            with open(cookies,"wb") as f:
                f.write(up.getbuffer())

        saved = []
        for vid in to_dl:
            t, u = vid["title"], vid["webpage_url"]
            st.write(f"▶️ {t}")
            opts = {
                "format":"bestaudio/best",
                "outtmpl": os.path.join("downloads","%(title)s.%(ext)s"),
                "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet": True,
            }
            if cookies:
                opts["cookiefile"] = cookies

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(u, download=True)
            except yt_dlp.utils.DownloadError as de:
                msg = str(de)
                if "Sign in to confirm your age" in msg:
                    st.error("⚠️ Age‑restricted—please upload cookies.txt")
                else:
                    st.error(f"❌ Failed {t}: {de}")
                continue

            fn = ydl.prepare_filename(info)
            mp3 = os.path.splitext(fn)[0] + ".mp3"
            saved.append(mp3)
            st.success(f"✅ {os.path.basename(mp3)}")

        st.write("### Save MP3s")
        for i, path in enumerate(saved):
            if os.path.exists(path):
                with open(path,"rb") as f:
                    st.download_button(
                        label=f"Save {os.path.basename(path)}",
                        data=f,
                        file_name=os.path.basename(path),
                        mime="audio/mpeg",
                        key=f"save_{i}",
                    )
            else:
                st.warning(f"Missing: {path}")
    elif not to_dl:
        st.info("Select at least one video above to download.")
