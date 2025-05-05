import os
import json
import streamlit as st
import yt_dlp
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)
from openai import OpenAI

# ————————————————————————————————————————————————————————————————
# Page configuration
st.set_page_config(
    page_title="DJ Set Tracklist & MP3 Downloader",
    layout="centered",
)
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# ————————————————————————————————————————————————————————————————
# Sidebar inputs
model_choice = st.sidebar.selectbox(
    "Choose OpenAI model:",
    ["gpt-4", "gpt-3.5-turbo"],
)
api_key = st.sidebar.text_input(
    "OpenAI API Key:",
    type="password",
)
limit = st.sidebar.number_input(
    "Max comments to fetch:",
    min_value=10,
    max_value=500,
    value=100,
)
sort_option = st.sidebar.selectbox(
    "Sort comments by:",
    ["recent", "popular"],
)
enable_dl = st.sidebar.checkbox(
    "Enable MP3 download",
    value=False,
)

# ————————————————————————————————————————————————————————————————
# Main input
video_url = st.text_input(
    "YouTube DJ Set URL",
    placeholder="https://www.youtube.com/watch?v=...",
)

# ————————————————————————————————————————————————————————————————
if st.button("Extract Tracks & Download"):
    # 1) Validate
    if not video_url.strip():
        st.error("Please enter a YouTube URL.")
        st.stop()
    if not api_key.strip():
        st.error("Please enter your OpenAI API key.")
        st.stop()

    # 2) Download comments via Python API
    st.info("Step 1: Downloading comments…")
    try:
        ycd = YoutubeCommentDownloader()
        sort_flag = (
            SORT_BY_RECENT
            if sort_option == "recent"
            else SORT_BY_POPULAR
        )
        comments = []
        for c in ycd.get_comments_from_url(
            video_url,
            sort_by=sort_flag,
        ):
            txt = c.get("text", "").strip()
            if txt:
                comments.append(txt)
            if len(comments) >= limit:
                break
        if not comments:
            raise RuntimeError("No comments returned.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 3) Prepare few‑shot GPT prompt
    st.info("Step 2: Extracting track names via GPT…")
    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are an expert at reading DJ set tracklists from YouTube comments "
        "and replying with pure JSON."
    )
    few_shot_example = (
        "Example input:\n"
        "Comments:\n"
        "12:34 Floating Points - Birth 4000\n"
        "22:10 Tiga & Hudson Mohawke - Untitled Codename Rimini\n\n"
        "Example output (JSON only):\n"
        "[\n"
        "  {\"artist\":\"Floating Points\",\"track\":\"Birth 4000\"},\n"
        "  {\"artist\":\"Tiga & Hudson Mohawke\",\"track\":\"Untitled Codename Rimini\"}\n"
        "]"
    )
    snippet = "\n".join(comments[:50])
    user_block = f"Comments:\n{snippet}"

    def extract_json(raw: str) -> str:
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def ask_model(model: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"assistant", "content":few_shot_example},
                {"role":"user",      "content":user_block},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    # 4) Try GPT-4 then fallback to GPT-3.5
    tracks = None
    used_model = None
    for m in [model_choice, "gpt-3.5-turbo"]:
        try:
            raw = ask_model(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, list) and parsed:
                tracks = parsed
                used_model = m
                break
        except Exception:
            continue

    if not tracks:
        st.error("GPT failed to extract any tracks.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks identified via {used_model}.")

    # 5) Show selection UI
    st.write("---")
    st.write("### Select tracks to download")
    options = []
    for t in tracks:
        artist = t.get("artist", "Unknown Artist")
        track  = t.get("track",  "Unknown Track")
        options.append(f"{artist} - {track}")

    selected = st.multiselect(
        "Choose tracks:",
        options=options,
        default=options,
    )

    # 6) Download MP3s
    if enable_dl and selected:
        st.info("Step 3: Downloading MP3s…")
        os.makedirs("downloads", exist_ok=True)
        ydl_opts = {
            "format":"bestaudio/best",
            "outtmpl": os.path.join("downloads","%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "postprocessors":[
                {"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}
            ],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for q in selected:
                st.write(f"▶️ {q}")
                try:
                    ydl.download([f"ytsearch1:{q}"])
                    st.write("Done")
                except Exception as dl_err:
                    st.error(f"Failed: {dl_err}")
        st.success("🎉 All selected tracks downloaded to `downloads/`.")
    elif enable_dl:
        st.warning("No tracks selected for download.")
