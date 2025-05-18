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

# BUNDLE IN FFmpeg AT RUNTIME
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
api_key = st.secrets.get("OPENAI_API_KEY", "")
COMMENT_LIMIT = 100
SORT_FLAG = SORT_BY_POPULAR
MODELS = ["gpt-4", "gpt-3.5-turbo"]

# ── FETCH FUNCTION ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_video_candidates(entries):
    ydl_opts = {"quiet": True, "skip_download": True, "extract_flat": True}
    vids = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for e in entries:
            query = f"{e['artist']} - {e['track']}"
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                video = info["entries"][0]
                vid_id = video.get("id") or video.get("url")
                thumbnail = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                vids.append({
                    "id": vid_id,
                    "title": video.get("title"),
                    "webpage_url": f"https://www.youtube.com/watch?v={vid_id}",
                    "thumbnail": thumbnail,
                })
            except Exception:
                vids.append(None)
    return vids

# ── USER INPUTS ────────────────────────────────────────────────────────────────
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
if st.button("Extract Tracks"):
    if not api_key:
        st.error("OpenAI API key is missing from your secrets!")
        st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()

    # Step 1: download comments
    st.info("Step 1: downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        raw_comments = downloader.get_comments_from_url(video_url, sort_by=SORT_FLAG)
        comments = [c.get("text", "") for c in raw_comments][:COMMENT_LIMIT]
        if not comments:
            raise RuntimeError("No comments found.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: extract tracklist via GPT
    st.info("Step 2: extracting track IDs…")
    client = OpenAI(api_key=api_key)
    system_prompt = (
        "You are a world-class DJ-set tracklist curator with a complete music knowledge base.\n"
        "Given raw YouTube comment texts, do two things:\n"
        "1) Extract all timestamped track mentions in the form: MM:SS Artist - Track Title (optional remix/version and [label])\n"
        "2) Extract any correction/update comments where a user writes 'edit:', 'correction:', 'update:', 'oops:', etc., clarifying a previous track.\n"
        "Return ONLY a JSON object with keys 'tracks' and 'corrections', each a list of objects with fields:\n"
        "  artist  (string)\n"
        "  track   (string)\n"
        "  version (string or empty)\n"
        "  label   (string or empty)\n"
        "No extra keys or commentary."
    )
    few_shot = (
        "### Example Input:\n"
        "Comments:\n03:45 John Noseda - Climax\n"
        "05:10 Roy - Shooting Star [1987]\n"
        "07:20 Cormac - Sparks\n"
        "10:00 edit: John Noseda - Climax (VIP Mix)\n\n"
        "### Example JSON Output:\n"
        "{\n  \"tracks\": [\n    {\"artist\":\"John Noseda\",\"track\":\"Climax\",\"version\":\"\",\"label\":\"\"},\n"
        "    {\"artist\":\"Roy\",\"track\":\"Shooting Star\",\"version\":\"\",\"label\":\"1987\"},\n"
        "    {\"artist\":\"Cormac\",\"track\":\"Sparks\",\"version\":\"\",\"label\":\"\"}\n  ],\n"
        "  \"corrections\": [\n    {\"artist\":\"John Noseda\",\"track\":\"Climax\",\"version\":\"VIP Mix\",\"label\":\"\"}\n  ]\n}"
    )
    snippet = "\n".join(comments)

    def extract_json(raw: str) -> str:
        m = re.search(r"\{[\s\S]*\}", raw)
        return m.group(0) if m else raw.strip()

    def ask_model(model_name: str) -> str:
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

    tracks, corrections, used = [], [], None
    for m in MODELS:
        try:
            raw_out = ask_model(m)
            clean = extract_json(raw_out)
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks = parsed["tracks"]
                corrections = parsed["corrections"]
                used = m
                break
        except Exception:
            continue

    if not used:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections.")
    all_entries = tracks + corrections
    st.session_state["dj_tracks"] = all_entries

# ── MANUAL TRACK SEARCH ─────────────────────────────────────────────────────────
st.write("---")
artist_input = st.text_input("Artist (manual search)", key="manual_artist")
track_input = st.text_input("Track Title (manual search)", key="manual_track")
if st.button("Search Tracks"):
    if not artist_input.strip() or not track_input.strip():
        st.error("Please enter both artist and track title.")
    else:
        manual_entries = [{"artist": artist_input.strip(), "track": track_input.strip()}]
        results = fetch_video_candidates(manual_entries)
        video = results[0]
        if not video:
            st.error(f"No YouTube match for **{artist_input} – {track_input}**")
        else:
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.image(video['thumbnail'], width=100)
            c2.markdown(f"**[{video['title']}]({video['webpage_url']})**")
            c2.caption(f"Search: `{artist_input} - {track_input}`")
            if c3.checkbox("Download", key="manual_download"):
                st.info("Downloading MP3…")
                os.makedirs("downloads", exist_ok=True)
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join("downloads", "%(+title)s.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                    "ffmpeg_location": FF_BIN,
                    "ffprobe_location": FP_BIN,
                    "quiet": True,
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video['webpage_url'], download=True)
                        mp3 = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
                    st.success(f"✅ {os.path.basename(mp3)}")
                    with open(mp3, "rb") as f:
                        data = f.read()
                    st.download_button(label=f"Download {os.path.basename(mp3)}", data=data, file_name=os.path.basename(mp3), mime="audio/mp3")
                except Exception as e:
                    st.error(f"Error downloading {artist_input} – {track_input}: {e}")

# ── EXTRACTED TRACKLIST PREVIEW & DOWNLOAD ─────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]
    st.write("### Tracks identified:")
    for idx, e in enumerate(entries, start=1):
        st.write(f"{idx}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview YouTube results (select checkbox to download)")
    results = fetch_video_candidates(entries)
    selections = []
    for i, vid in enumerate(results):
        entry = entries[i]
        if not vid:
            st.error(f"No match for {entry['artist']} – {entry['track']}")
            continue
        col1, col2, col3 = st.columns([1, 4, 1])
        col1.image(vid['thumbnail'], width=100)
        col2.markdown(f"**[{vid['title']}]({vid['webpage_url']})**")
        col2.caption(f"Search: `{entry['artist']} - {entry['track']}`")
        if col3.checkbox("", key=f"select_{i}"):
            selections.append(vid)

    st.write("---")
    if selections and st.button("Download Selected MP3s"):
        st.info("Downloading MP3s…")
        os.makedirs("downloads", exist_ok=True)
        saved = []
        for vid in selections:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet": True,
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(vid['webpage_url'], download=True)
                    mp3 = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
                    saved.append(mp3)
                st.success(f"✅ {os.path.basename(mp3)}")
            except Exception as e:
                st.error(f"Error downloading {vid['title']}: {e}")

        for path in saved:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                st.download_button(label=f"Download {os.path.basename(path)}", data=data, file_name=os.path.basename(path), mime="audio/mp3")
    else:
        st.info("Select at least one track to enable download.")
        
