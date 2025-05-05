import os
import json

import streamlit as st
import yt_dlp
from openai import OpenAI
from youtube_comment_downloader.downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR,
)

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="centered")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# Sidebar
model_choice = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.sidebar.text_input("OpenAI API Key:", type="password")
limit        = st.sidebar.number_input("Max comments to fetch:", 10, 500, 100)
sort_option  = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])
enable_dl    = st.sidebar.checkbox("Enable MP3 download", value=False)

# Main input
video_url = st.text_input("YouTube DJ Set URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Extract & Download"):
    # Step 1: Download comments
    st.info("Step 1: Downloading comments…")
    try:
        downloader = YoutubeCommentDownloader()
        sort_flag = SORT_BY_RECENT if sort_option == "recent" else SORT_BY_POPULAR
        comments = []
        for c in downloader.get_comments_from_url(video_url, sort_by=sort_flag):
            comments.append(c.get("text", ""))
            if len(comments) >= limit:
                break
        if not comments:
            raise RuntimeError("No comments returned.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Use GPT to extract tracks
    st.info("Step 2: Extracting track names via GPT…")
    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are an expert at reading DJ-set tracklists from YouTube comments "
        "and returning a pure JSON list of {artist, track} objects."
    )
    few_shot_example = (
        "Example input:\n"
        "Comments:\n"
        "12:34 Floating Points - Birth 4000\n"
        "22:10 Tiga & Hudson Mohawke - Untitled Codename Rimini\n\n"
        "Example output (JSON only):\n"
        "[\n"
        "  {\"artist\": \"Floating Points\", \"track\": \"Birth 4000\"},\n"
        "  {\"artist\": \"Tiga & Hudson Mohawke\", \"track\": \"Untitled Codename Rimini\"}\n"
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

    def ask(model_name: str) -> tuple[list[dict], str]:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system",    "content": system_prompt},
                {"role": "assistant", "content": few_shot_example},
                {"role": "user",      "content": user_block},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content
        clean = extract_json(raw)
        data = json.loads(clean)
        return data, model_name

    tracks = []
    used_model = ""
    for m in [model_choice, "gpt-3.5-turbo"]:
        try:
            data, used = ask(m)
            if isinstance(data, list) and data:
                tracks = data
                used_model = used
                break
        except Exception:
            continue

    if not tracks:
        st.error("GPT failed to extract any tracks.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks identified via {used_model}.")

    # Step 3: Track selection UI
    st.write("---")
    st.write("### Select tracks to download")
    labels = [
        f"{t.get('artist', 'Unknown Artist')} - {t.get('track', 'Unknown Track')}"
        for t in tracks
    ]
    selected = st.multiselect("Choose tracks:", options=labels, default=labels)

    # Step 4: Download MP3s
    if enable_dl:
        if not selected:
            st.warning("No tracks selected.")
        else:
            st.info("Step 3: Downloading MP3s…")
            os.makedirs("downloads", exist_ok=True)
            for q in selected:
                st.write(f"▶️ {q}")
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join("downloads", "%(title)s.%(ext)s"),
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"ytsearch1:{q}", download=True)
                        fn = ydl.prepare_filename(info)
                    st.success(f"✅ Downloaded to `{fn}`")
                except Exception as e:
                    st.error(f"❌ Failed to download {q}: {e}")

    st.balloons()
