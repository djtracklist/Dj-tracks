import os import requests import tarfile import stat import json import re

import streamlit as st import yt_dlp from openai import OpenAI from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

BUNDLE IN FFmpeg AT RUNTIME

FF_DIR = "ffmpeg-static" FF_BIN = os.path.join(FF_DIR, "ffmpeg") FP_BIN = os.path.join(FF_DIR, "ffprobe")

def ensure_ffmpeg(): if os.path.isfile(FF_BIN) and os.path.isfile(FP_BIN): return os.makedirs(FF_DIR, exist_ok=True) url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" local_tar = os.path.join(FF_DIR, "ffmpeg.tar.xz") with requests.get(url, stream=True) as r: r.raise_for_status() with open(local_tar, "wb") as f: for chunk in r.iter_content(chunk_size=8192): f.write(chunk) with tarfile.open(local_tar, mode="r:xz") as tar: for member in tar.getmembers(): name = os.path.basename(member.name) if name in ("ffmpeg", "ffprobe"): member.name = name tar.extract(member, FF_DIR) os.remove(local_tar) os.chmod(FF_BIN, stat.S_IXUSR | stat.S_IRUSR) os.chmod(FP_BIN, stat.S_IXUSR | stat.S_IRUSR)

ensure_ffmpeg()

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered") st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

CONFIG

api_key = st.secrets.get("OPENAI_API_KEY", "") COMMENT_LIMIT = 100 SORT_FLAG = SORT_BY_POPULAR MODELS = ["gpt-4", "gpt-3.5-turbo"]

Inputs

video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...") artist_input = st.text_input("Artist (optional)", "") track_input = st.text_input("Track Title (optional)", "")

if st.button("Extract Tracks"): if not api_key: st.error("OpenAI API key is missing from your secrets!") st.stop() if not video_url.strip() and not (artist_input.strip() and track_input.strip()): st.error("Please enter a YouTube URL or provide both Artist and Track Title.") st.stop()

all_entries = []

# Extract from YouTube comments
if video_url.strip():
    st.info("Step 1: reviewing comments…")
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
        m = re.search(r"{[\s\S]*}", raw)
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
            raw = ask(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model = m
                break
        except Exception:
            continue

    if used_model is None:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections.")
    all_entries = tracks + corrections

# Append manual entry if provided
if artist_input.strip() and track_input.strip():
    all_entries.append({
        "artist": artist_input.strip(),
        "track": track_input.strip(),
        "version": "",
        "label": ""
    })

st.session_state["dj_tracks"] = all_entries

Display extracted entries and allow selection

if "dj_tracks" in st.session_state: all_entries = st.session_state["dj_tracks"]

st.write("### Tracks identified:")
for i, e in enumerate(all_entries, start=1):
    st.write(f"{i}. {e['artist']} – {e['track']}")

st.write("---")
st.write("### Preview YouTube results (select checkbox to download)")

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

video_results = fetch_video_candidates(all_entries)
to_download = []

for idx, video in enumerate(video_results):
    entry = all_entries[idx]
    if video is None:
        st.error(f"No YouTube match for **{entry['artist']} – {entry['track']}**")
        continue

    cols = st.columns([1, 4, 1])
    cols[0].image(video["thumbnail"], width=100)
    cols[1].markdown(f"**[{video['title']}]({video['webpage_url']})**")
    cols[1].caption(f"Search: `{entry['artist']} - {entry['track']}`")
    if cols[2].checkbox("", key=f"vid_{idx}"):
        to_download.append(video)

st.write("---")
if to_download and st.button("Download Selected MP3s"):
    st.info("Preparing selected tracks…")
    os.makedirs("downloads", exist_ok=True)
    saved = []

    for video in to_download:
        title = video["title"]
        url = video["webpage_url"]
        st.write(f"▶️ {title}")
        ydl_opts = {
            "format": "bestaudio/best", 
            "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
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
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                orig = ydl.prepare_filename(info)
                mp3 = os.path.splitext(orig)[0] + ".mp3"
                saved.append(mp3)
            st.success(f"✅ {os.path.basename(mp3)}")
        except Exception as e:
            st.error(f"❌ Failed to download {title}: {e}")

    # Offer individual MP3 downloads
    if saved:
        for path in saved:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                st.download_button(
                    label=f"Download {os.path.basename(path)}",
                    data=data,
                    file_name=os.path.basename(path),
                    mime="audio/mp3",
                )
    else:
        st.warning("No files were downloaded successfully.")
elif not to_download:
    st.info("Select at least one video above to enable downloading.")

# Manual Track Search (after setlist preview)
st.write("---")
st.write("### Manual Track Search")
manual_artist = st.text_input("Artist", key="manual_artist")
manual_track = st.text_input("Track Title", key="manual_track")
if st.button("Search Track"):
    if not manual_artist.strip() or not manual_track.strip():
        st.error("Please enter both artist and track title.")
    else:
        manual_entries = [{"artist": manual_artist.strip(), "track": manual_track.strip()}]
        manual_results = fetch_video_candidates(manual_entries)
        video = manual_results[0]
        if video is None:
            st.error(f"No YouTube match for **{manual_artist} – {manual_track}**")
        else:
            cols = st.columns([1, 4, 1])
            cols[0].image(video["thumbnail"], width=100)
            cols[1].markdown(f"**[{video['title']}]({video['webpage_url']})**")
            cols[1].caption(f"Search: `{manual_artist} - {manual_track}`")
            if cols[2].checkbox("Download", key="manual_vid"):
                st.info("Downloading MP3…")
                os.makedirs("downloads", exist_ok=True)
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
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
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video["webpage_url"], download=True)
                        orig = ydl.prepare_filename(info)
                        mp3 = os.path.splitext(orig)[0] + ".mp3"
                    st.success(f"✅ {os.path.basename(mp3)}")

