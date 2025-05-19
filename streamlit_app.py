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
api_key = st.secrets.get("OPENAI_API_KEY", "")
COMMENT_LIMIT = 100
SORT_FLAG = SORT_BY_POPULAR
MODELS = ["gpt-4", "gpt-3.5-turbo"]

# ── UTIL: Fetch YouTube search results ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_video_candidates(entries):
    ydl_opts = {"quiet": True, "skip_download": True, "extract_flat": True}
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
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...", key="url_input")
if st.button("Extract Tracks", key="extract_setlist"):
    if not api_key:
        st.error("OpenAI API key is missing!")
        st.stop()
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()

    # download comments
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

    # GPT extraction
    st.info("Step 2: extracting track IDs…")
    client = OpenAI(api_key=api_key)
    system_prompt = (
        "You are a world-class DJ-set tracklist curator.\n"
        "Given raw YouTube comments, extract timestamped tracks and corrections.\n"
        "Return ONLY JSON with 'tracks' and 'corrections' lists (fields: artist, track, version, label)."
    )
    few_shot = (
        "### Example Input:\nComments:\n03:45 Artist A - Song A\n05:10 Artist B - Song B [2010]\n\n"
        "### Example JSON Output:\n{ 'tracks': [...], 'corrections': [...] }"
    )
    snippet = "\n".join(comments)

    def extract_json(raw: str) -> str:
        match = re.search(r"\{[\s\S]*\}", raw)
        return match.group(0) if match else raw.strip()

    tracks, corrections = [], []
    used_model = None
    for model in MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "assistant", "content": few_shot},
                    {"role": "user", "content": f"Comments:\n{snippet}"}
                ],
                temperature=0
            )
            out = resp.choices[0].message.content
            js = extract_json(out)
            parsed = json.loads(js)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model = model
                break
        except Exception:
            continue

    if not used_model:
        st.error("❌ GPT failed to extract tracklist.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections.")
    st.session_state["dj_tracks"] = tracks + corrections

# ── SECTION: Manual Track Search ─────────────────────────────────────────────────
st.write("---")
st.write("### Manual Track Search")
artist_manual = st.text_input("Artist", key="manual_artist")
track_manual = st.text_input("Track Title", key="manual_track")
if st.button("Search Tracks", key="search_manual"):
    if not artist_manual.strip() or not track_manual.strip():
        st.error("Please enter both artist and track title.")
    else:
        entry = {"artist": artist_manual.strip(), "track": track_manual.strip()}
        result = fetch_video_candidates([entry])[0]
        if result:
            st.session_state["manual_video"] = result
            st.session_state.pop("manual_mp3", None)
        else:
            st.session_state.pop("manual_video", None)
            st.error(f"No YouTube match for {artist_manual} – {track_manual}")

# Display and Download Manual Result
if "manual_video" in st.session_state:
    video = st.session_state["manual_video"]
    c1, c2, c3 = st.columns([1,4,1])
    c1.image(video['thumbnail'], width=100)
    c2.markdown(f"**[{video['title']}]({video['webpage_url']})**")
    c2.caption(f"Search: `{artist_manual} - {track_manual}`")
    if c3.button("Download MP3", key="download_manual"):
        st.info("Downloading MP3…")
        os.makedirs("downloads", exist_ok=True)
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "ffmpeg_location": FF_BIN,
            "ffprobe_location": FP_BIN,
            "quiet": True
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video['webpage_url'], download=True)
                mp3 = ydl.prepare_filename(info).rsplit('.',1)[0] + ".mp3"
            st.success(f"✅ {os.path.basename(mp3)}")
            st.session_state["manual_mp3"] = mp3
        except Exception as e:
            st.error(f"Error downloading {artist_manual} – {track_manual}: {e}")

# Show Download Button if ready
if "manual_mp3" in st.session_state:
    path = st.session_state["manual_mp3"]
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        st.download_button(label=f"Download {os.path.basename(path)}", data=data, file_name=os.path.basename(path), mime="audio/mp3")

# ── SECTION: Extracted Tracklist Preview & Download ─────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]
    st.write("### Tracks identified:")
    for idx, e in enumerate(entries, start=1):
        st.write(f"{idx}. {e['artist']} – {e['track']}")
    st.write("---")
    st.write("### Preview YouTube results (select which to download)")
    candidates = fetch_video_candidates(entries)
    to_download = []
    for i, vid in enumerate(candidates):
        entry = entries[i]
        if not vid:
            st.error(f"No match for {entry['artist']} – {entry['track']}")
            continue
        col1, col2, col3 = st.columns([1, 4, 1])
        col1.image(vid['thumbnail'], width=100)
        col2.markdown(f"**[{vid['title']}]({vid['webpage_url']})**")
        col2.caption(f"Search: `{entry['artist']} - {entry['track']}`")
        if col3.checkbox("", key=f"select_{i}"):
            to_download.append(vid)

    st.write("---")
    # Trigger downloads and store list in session state
    if to_download and st.button("Download Selected MP3s", key="download_selected"):
        st.info("Downloading MP3s…")
        os.makedirs("downloads", exist_ok=True)
        downloaded = []
        for vid in to_download:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet": True
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(vid['webpage_url'], download=True)
                    mp3 = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
                    downloaded.append(mp3)
                st.success(f"✅ {os.path.basename(mp3)}")
            except Exception as ex:
                st.error(f"Error downloading {vid['title']}: {ex}")
        st.session_state["downloaded_tracks"] = downloaded

    # Render persistent download buttons
    if "downloaded_tracks" in st.session_state:
        for path in st.session_state["downloaded_tracks"]:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                st.download_button(
                    label=f"Download {os.path.basename(path)}",
                    data=data,
                    file_name=os.path.basename(path),
                    mime="audio/mp3",
                )
    elif not to_download:
        st.info("Select at least one track to enable download.")
        
