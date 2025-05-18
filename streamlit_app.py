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

# CONFIGURATION
api_key = st.secrets.get("OPENAI_API_KEY", "")
COMMENT_LIMIT = 100
SORT_FLAG = SORT_BY_POPULAR
MODELS = ["gpt-4", "gpt-3.5-turbo"]

# INPUT FIELDS
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
artist_input = st.text_input("Artist (optional)", "")
track_input = st.text_input("Track Title (optional)", "")

if st.button("Extract Tracks"):
    # Validate inputs
    if not api_key:
        st.error("OpenAI API key is missing from your secrets!")
        st.stop()
    if not video_url.strip() and not (artist_input.strip() and track_input.strip()):
        st.error("Please enter a YouTube URL or provide both Artist and Track Title.")
        st.stop()

    all_entries = []

    # 1. Extract from YouTube comments via GPT
    if video_url.strip():
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
            "Comments:\n"
            "03:45 John Noseda - Climax\n"
            "05:10 Roy - Shooting Star [1987]\n"
            "07:20 Cormac - Sparks\n"
            "10:00 edit: John Noseda - Climax (VIP Mix)\n\n"
            "### Example JSON Output:\n"
            "{\n"
            "  \"tracks\": [\n"
            "    {\"artist\":\"John Noseda\",\"track\":\"Climax\",\"version\":\"\",\"label\":\"\"},\n"
            "    {\"artist\":\"Roy\",\"track\":\"Shooting Star\",\"version\":\"\",\"label\":\"1987\"},\n"
            "    {\"artist\":\"Cormac\",\"track\":\"Sparks\",\"version\":\"\",\"label\":\"\"}\n"
            "  ],\n"
            "  \"corrections\": [\n"
            "    {\"artist\":\"John Noseda\",\"track\":\"Climax\",\"version\":\"VIP Mix\",\"label\":\"\"}\n"
            "  ]\n"
            "}"
        )
        snippet = "\n".join(comments)

        def extract_json(raw: str) -> str:
            match = re.search(r"\{[\s\S]*\}", raw)
            return match.group(0) if match else raw.strip()

        def ask_model(model_name: str) -> str:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "assistant", "content": few_shot},
                    {"role": "user", "content": f"Comments:\n{snippet}"},
                ],
                temperature=0,
            )
            return response.choices[0].message.content

        tracks, corrections, used = [], [], None
        for model in MODELS:
            try:
                raw_output = ask_model(model)
                json_str = extract_json(raw_output)
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                    tracks = parsed["tracks"]
                    corrections = parsed["corrections"]
                    used = model
                    break
            except Exception:
                continue

        if not used:
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

# DISPLAY & DOWNLOAD SECTION
if "dj_tracks" in st.session_state:
    all_entries = st.session_state["dj_tracks"]

    st.write("### Tracks identified:")
    for idx, entry in enumerate(all_entries, start=1):
        st.write(f"{idx}. {entry['artist']} – {entry['track']}")

    st.write("---")
    st.write("### Preview YouTube results (select checkbox to download)")

    @st.cache_data(show_spinner=False)
    def fetch_video_candidates(entries):
        opts = {"quiet": True, "skip_download": True, "extract_flat": True}
        results = []
        with yt_dlp.YoutubeDL(opts) as ydl:
            for e in entries:
                query = f"{e['artist']} - {e['track']}"
                try:
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    vid = info["entries"][0]
                    vid_id = vid.get("id") or vid.get("url")
                    results.append({
                        "id": vid_id,
                        "title": vid.get("title"),
                        "webpage_url": f"https://www.youtube.com/watch?v={vid_id}",
                        "thumbnail": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                    })
                except Exception:
                    results.append(None)
        return results

    video_results = fetch_video_candidates(all_entries)
    selections = []
    for i, video in enumerate(video_results):
        entry = all_entries[i]
        if video is None:
            st.error(f"No match for {entry['artist']} – {entry['track']}")
            continue
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.image(video['thumbnail'], width=100)
        c2.markdown(f"**[{video['title']}]({video['webpage_url']})**")
        c2.caption(f"Search: `{entry['artist']} - {entry['track']}`")
        if c3.checkbox("", key=f"select_{i}"):
            selections.append(video)

    st.write("---")
    if selections and st.button("Download Selected MP3s"):
        st.info("Downloading MP3s…")
        os.makedirs("downloads", exist_ok=True)
        downloaded = []
        for vid in selections:
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
                    info = ydl.extract_info(vid['webpage_url'], download=True)
                    filename = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"
                    downloaded.append(filename)
                st.success(f"✅ {os.path.basename(filename)}")
            except Exception as ex:
                st.error(f"Error downloading {vid['title']}: {ex}")

        for path in downloaded:
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
        st.info("Select at least one track to enable download.")

    # MANUAL TRACK SEARCH (After setlist)
    st.write("---")
    st.write("### Manual Track Search")
    m_artist = st.text_input("Artist", key="manual_artist")
    m_track  = st.text_input("Track Title", key="manual_track")
    if st.button("Search Track"):
        if not m_artist.strip() or not m_track.strip():
            st.error("Please enter both artist and track title.")
        else:
            manual = [{"artist": m_artist.strip(), "track": m_track.strip()}]
            results = fetch_video_candidates(manual)
            vid = results[0]
            if not vid:
                st.error(f"No match for {m_artist} – {m_track}")
            else:
                col1, col2, col3 = st.columns([1,4,1])
                col1.image(vid['thumbnail'], width=100)
                col2.markdown(f"**[{vid['title']}]({vid['webpage_url']})**")
                col2.caption(f"Search: `{m_artist} - {m_track}`")
                if col3.checkbox("Download", key="manual_dl"):
                    st.info("Downloading MP3…")
                    os.makedirs("downloads", exist_ok=True)
                    opts = ydl_opts.copy()
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(vid['webpage_url'], download=True)
                            fn = ydl.prepare_filename(info).rsplit('.',1)[0] + ".mp3"
                        st.success(f"✅ {os.path.basename(fn)}")
                        with open(fn, "rb") as f:
                            data = f.read()
                        st.download_button(label=f"Download {os.path.basename(fn)}", data=data, file_name=os.path.basename(fn), mime="audio/mp3")
                    except Exception as e:
                        st.error(f"Error: {e}")
