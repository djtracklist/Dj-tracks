import os
import requests
import tarfile
import stat
import json
import re

import streamlit as st
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyOAuth
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
    # Download archive
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_tar, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    # Extract binaries, catching truncated‐archive errors
    try:
        with tarfile.open(local_tar, mode="r:xz") as tar:
            for member in tar.getmembers():
                name = os.path.basename(member.name)
                if name in ("ffmpeg", "ffprobe"):
                    member.name = name
                    try:
                        tar.extract(member, FF_DIR)
                    except (EOFError, tarfile.ReadError) as e:
                        st.warning(f"Warning: failed to extract {name}: {e}")
                        continue
    except (EOFError, tarfile.ReadError) as e:
        st.error(f"Error unpacking ffmpeg archive: {e}")
    finally:
        if os.path.exists(local_tar):
            os.remove(local_tar)
    # Fix permissions
    try:
        os.chmod(FF_BIN, stat.S_IXUSR | stat.S_IRUSR)
        os.chmod(FP_BIN, stat.S_IXUSR | stat.S_IRUSR)
    except Exception as perm_err:
        st.warning(f"Could not set FFmpeg permissions: {perm_err}")

ensure_ffmpeg()

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# ── CONFIGURATION ──────────────────────────────────────────────────────────────
OPENAI_API_KEY       = st.secrets.get("OPENAI_API_KEY", "")
SPOTIFY_CLIENT_ID     = st.secrets.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = st.secrets.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI  = st.secrets.get("SPOTIFY_REDIRECT_URI", "http://localhost:8501/")

COMMENT_LIMIT = 100
SORT_FLAG     = SORT_BY_POPULAR
MODELS        = ["gpt-4", "gpt-3.5-turbo"]

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
                video = info.get("entries", [None])[0]
                if not video:
                    vids.append(None)
                else:
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

# ── USER INPUT: YouTube URL & Extract Tracks ──────────────────────────────────
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")
if st.button("Extract Tracks", key="btn_extract"):
    if not OPENAI_API_KEY:
        st.error("OpenAI API key is missing!")
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
    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = (
        "You are a world-class DJ-set tracklist curator.\n"
        "Given raw YouTube comment texts, extract timestamped tracks and corrections.\n"
        "Return ONLY JSON with 'tracks' and 'corrections' lists (fields: artist, track, version, label)."
    )
    few_shot = (
        "### Example Input:\n"
        "Comments:\n03:45 John Noseda - Climax\n"
        "05:10 Roy - Shooting Star [1987]\n07:20 Cormac - Sparks\n"
        "10:00 edit: John Noseda - Climax (VIP Mix)\n\n"
        "### Example JSON Output:\n"
        "{ 'tracks': [ {'artist':'John Noseda','track':'Climax','version':'','label':''}, ... ], 'corrections':[ ... ] }"
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

    tracks, corrections, used_model = [], [], None
    for m in MODELS:
        try:
            raw_output = ask_model(m)
            json_str   = extract_json(raw_output)
            parsed     = json.loads(json_str)
            if isinstance(parsed, dict) and "tracks" in parsed and "corrections" in parsed:
                tracks      = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model  = m
                break
        except Exception:
            continue

    if not used_model:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections.")
    st.session_state["dj_tracks"] = tracks + corrections

# ── MANUAL TRACK SEARCH ─────────────────────────────────────────────────────────
st.write("---")
st.subheader("Manual Track Search")
artist_manual = st.text_input("Artist", key="manual_artist")
track_manual  = st.text_input("Track Title", key="manual_track")
if st.button("Search Track", key="btn_manual_search"):
    if not artist_manual.strip() or not track_manual.strip():
        st.error("Please enter both artist and track title.")
    else:
        st.session_state["manual_video"] = fetch_video_candidates(
            [{"artist": artist_manual.strip(), "track": track_manual.strip()}]
        )[0]

if "manual_video" in st.session_state:
    vid = st.session_state["manual_video"]
    if vid:
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.image(vid["thumbnail"], width=100)
        c2.markdown(f"**[{vid['title']}]({vid['webpage_url']})**")
        c2.caption(f"Search: `{artist_manual} - {track_manual}`")
        if st.button("Download Manual MP3", key="btn_manual_download"):
            os.makedirs("downloads", exist_ok=True)
            opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(vid["webpage_url"], download=True)
                mp3  = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
            st.success(f"✅ Downloaded {os.path.basename(mp3)}")
            with open(mp3, "rb") as f:
                data = f.read()
            st.download_button(
                label=f"Download {os.path.basename(mp3)}",
                data=data,
                file_name=os.path.basename(mp3),
                mime="audio/mp3",
                key="btn_manual_dl_button"
            )
    else:
        st.error(f"No match for {artist_manual} – {track_manual}")

# ── EXTRACTED TRACKLIST PREVIEW & DOWNLOAD ─────────────────────────────────────
if "dj_tracks" in st.session_state:
    entries = st.session_state["dj_tracks"]
    st.write("### Tracks identified:")
    for idx, e in enumerate(entries, start=1):
        st.write(f"{idx}. {e['artist']} – {e['track']}")

    st.write("---")
    st.write("### Preview YouTube results (select checkbox to download)")
    results = fetch_video_candidates(entries)
    to_download = []
    for i, vid in enumerate(results):
        entry = entries[i]
        if not vid:
            st.error(f"No match for {entry['artist']} – {entry['track']}")
            continue
        col1, col2, col3 = st.columns([1, 4, 1])
        col1.image(vid["thumbnail"], width=100)
        col2.markdown(f"**[{vid['title']}]({vid['webpage_url']})**")
        col2.caption(f"Search: `{entry['artist']} - {entry['track']}`")
        if col3.checkbox("Select", key=f"sel_{i}"):
            to_download.append(vid)

    st.write("---")
    if to_download and st.button("Download Selected MP3s", key="btn_bulk_download"):
        os.makedirs("downloads", exist_ok=True)
        st.session_state.setdefault("downloaded_tracks", [])
        for vid in to_download:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                "postprocessors": [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
                "ffmpeg_location": FF_BIN,
                "ffprobe_location": FP_BIN,
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(vid["webpage_url"], download=True)
                mp3  = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
            st.session_state["downloaded_tracks"].append(mp3)
            st.success(f"✅ Downloaded {os.path.basename(mp3)}")

    if st.session_state.get("downloaded_tracks"):
        st.write("---")
        for idx, path in enumerate(st.session_state["downloaded_tracks"]):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                st.download_button(
                    label=f"Download {os.path.basename(path)}",
                    data=data,
                    file_name=os.path.basename(path),
                    mime="audio/mp3",
                    key=f"persist_dl_{idx}"
                )

# ── EXPORT TO SPOTIFY ───────────────────────────────────────────────────────────
if "dj_tracks" in st.session_state:
    st.write("---")
    st.subheader("Export to Spotify")

    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope="playlist-modify-public",
        show_dialog=True,
    )

    if "spotify_auth_url" not in st.session_state:
        st.session_state["spotify_auth_url"] = sp_oauth.get_authorize_url()
    st.markdown(f"[1. Authorize with Spotify]({st.session_state['spotify_auth_url']})")

    params = st.experimental_get_query_params()
    code = params.get("code", [None])[0]
    if code and "spotify_token" not in st.session_state:
        try:
            token_info = sp_oauth.get_access_token(code)
            st.session_state["spotify_token"] = token_info["access_token"]
            st.success("✅ Spotify authorization successful!")
        except Exception as e:
            st.error(f"Spotify auth failed: {e}")

    if st.session_state.get("spotify_token"):
        if st.button("Create Spotify Playlist", key="btn_spotify_export"):
            sp = spotipy.Spotify(auth=st.session_state["spotify_token"])
            uris = []
            for t in st.session_state["dj_tracks"]:
                q = f"{t['artist']} {t['track']}"
                res = sp.search(q=q, type="track", limit=1)
                items = res.get("tracks", {}).get("items", [])
                if items:
                    uris.append(items[0]["uri"])
                else:
                    st.warning(f"No Spotify match for {q}")
            if uris:
                user_id = sp.current_user()["id"]
                playlist = sp.user_playlist_create(
                    user=user_id,
                    name="My DJ Set Playlist",
                    public=True,
                )
                sp.playlist_add_items(playlist["id"], uris)
                st.success(f"🔗 Playlist created: {playlist['external_urls']['spotify']}")
            else:
                st.error("No tracks found; playlist not created.")
