import os
import requests
import tarfile
import stat
import io
import zipfile
import json
import re

import streamlit as st
import yt_dlp
from openai import OpenAI
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_POPULAR,
)

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

# ── CONFIG ────────────────────────────────────────────────────────────────────────
api_key = st.secrets.get("OPENAI_API_KEY", "")
COMMENT_LIMIT = 100
SORT_FLAG = SORT_BY_POPULAR
MODELS = ["gpt-4", "gpt-3.5-turbo"]

# ── INPUTS ────────────────────────────────────────────────────────────────────────
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
artist     = st.text_input("Or enter Artist name")
track_ttl  = st.text_input("And Track Title")
col1, col2 = st.columns(2)
with col1:
    extract_btn = st.button("Extract Tracks")
with col2:
    search_btn = st.button("Search by Artist/Title")

# ── FLOW A: COMMENT → GPT extraction ──────────────────────────────────────────────
if extract_btn and video_url:
    if not api_key:
        st.error("OpenAI API key is missing from your secrets!"); st.stop()
    st.info("Step 1: reviewing comments…")
    try:
        downloader   = YoutubeCommentDownloader()
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=SORT_FLAG)
        comments     = [c.get("text","") for c in raw_comments][:COMMENT_LIMIT]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}"); st.stop()

    st.info("Step 2: extracting Track IDs…")
    client = OpenAI(api_key=api_key)

    system_prompt = """
You are a world-class DJ-set tracklist curator with a complete music knowledge base.
Given raw YouTube comment texts, do two things:
1) Extract all track mentions in the form:
   [optional MM:SS] Artist - Track Title (optional remix/version and [label])
2) Extract any corrections (edit:, correction:, update:, oops:) clarifying a previous track.

Return ONLY a JSON with "tracks" and "corrections", each a list of {artist,track,version,label}.
"""
    few_shot = """
### Example Input:
Comments:
03:45 John Noseda - Climax
Artist Zed – No Time Stamp Track

### Example Output:
{
  "tracks":[
    {"artist":"John Noseda","track":"Climax","version":"","label":""},
    {"artist":"Artist Zed","track":"No Time Stamp Track","version":"","label":""}
  ],
  "corrections":[]
}
"""
    snippet = "\n".join(comments[:100])

    def extract_json(raw):
        m = re.search(r'\{[\s\S]*\}', raw)
        return m.group(0) if m else raw.strip()

    def ask(model):
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":system_prompt},
                {"role":"assistant","content":few_shot},
                {"role":"user","content":f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks, corrections, used = [], [], None
    for m in MODELS:
        try:
            raw_parsed = extract_json(ask(m))
            js = json.loads(raw_parsed)
            if "tracks" in js and "corrections" in js:
                tracks, corrections, used = js["tracks"], js["corrections"], m
                break
        except:
            pass

    # ── fallback regex if GPT finds nothing ─────────────────────────────
    if used is None:
        # 1) timestamped
        for c in comments:
            m1 = re.search(r'(\d{1,2}:\d{2})\s*([^–\-\n]+?)\s*[–\-]\s*(.+)', c)
            if m1:
                tracks.append({
                  "artist": m1.group(2).strip(),
                  "track":  m1.group(3).strip(),
                  "version":"", "label":""
                })
        # 2) no timestamp
        if not tracks:
            pat2 = re.compile(r'^\s*([\w &\'.,]+?)\s*[–\-]\s*(.+)$')
            for c in comments:
                m2 = pat2.match(c)
                if m2:
                    tracks.append({
                      "artist": m2.group(1).strip(),
                      "track":  m2.group(2).strip(),
                      "version":"", "label":""
                    })
        if tracks:
            used = "regex-fallback"
        else:
            st.error("❌ GPT failed to extract any tracks or corrections."); st.stop()

    all_entries = tracks + corrections
    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections.")
    st.session_state["dj_tracks"] = all_entries

# ── FLOW B: DIRECT ARTIST/TRACK SEARCH ───────────────────────────────────────────
elif search_btn and artist and track_ttl:
    st.session_state["dj_tracks"] = [{
        "artist": artist.strip(),
        "track":  track_ttl.strip(),
        "version": "", "label": ""
    }]

# ── PREVIEW & DOWNLOAD ──────────────────────────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]

    st.write("### Tracks identified:")
    for i,e in enumerate(entries,1):
        st.write(f"{i}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview YouTube results (select checkbox to download)")

    @st.cache_data(show_spinner=False)
    def fetch_video_candidates(ents):
        ydl_opts = {"quiet":True,"skip_download":True,"extract_flat":True}
        vids = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for e in ents:
                q = f"{e['artist']} - {e['track']}"
                try:
                    info = ydl.extract_info(f"ytsearch1:{q}", download=False)
                    vid = info["entries"][0]
                    vid_id = vid.get("id") or vid.get("url")
                    vids.append({
                      "id": vid_id,
                      "title": vid.get("title"),
                      "webpage_url": f"https://youtu.be/{vid_id}",
                      "thumbnail":   f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                    })
                except:
                    vids.append(None)
        return vids

    video_results = fetch_video_candidates(entries)
    to_dl = []
    for idx, video in enumerate(video_results):
        ent = entries[idx]
        if video is None:
            st.error(f"No match for **{ent['artist']} – {ent['track']}**")
            continue
        c0, c1, c2 = st.columns([1,4,1])
        c0.image(video["thumbnail"], width=100)
        c1.markdown(f"**[{video['title']}]({video['webpage_url']})**")
        c1.caption(f"Search: `{ent['artist']} - {ent['track']}`")
        if c2.checkbox("", key=f"vid_{idx}"):
            to_dl.append(video)

    st.write("---")
    if to_dl and st.button("Download Selected MP3s"):
        st.info("Preparing selected tracks…")
        os.makedirs("downloads", exist_ok=True)
        saved=[]
        for video in to_dl:
            st.write(f"▶️ {video['title']}")
            opts = {
              "format":"bestaudio/best",
              "outtmpl":os.path.join("downloads","%(title)s.%(ext)s"),
              "postprocessors":[{
                "key":"FFmpegExtractAudio",
                "preferredcodec":"mp3",
                "preferredquality":"192"
              }],
              "ffmpeg_location":FF_BIN,
              "ffprobe_location":FP_BIN,
              "quiet":True
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(video["webpage_url"], download=True)
                    orig = ydl.prepare_filename(info)
                    mp3  = os.path.splitext(orig)[0]+".mp3"
                    saved.append(mp3)
                st.success(f"✅ {os.path.basename(mp3)}")
            except Exception as e:
                st.error(f"❌ Failed to download {video['title']}: {e}")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf,"w") as zf:
            for p in saved:
                if os.path.exists(p):
                    zf.write(p, arcname=os.path.basename(p))
        buf.seek(0)
        if saved:
            st.download_button(
              "Download All as ZIP",
              data=buf,
              file_name="dj_tracks.zip",
              mime="application/zip"
            )
        else:
            st.warning("No files were downloaded successfully.")
    elif not to_dl:
        st.info("Select at least one video above to enable downloading.")
