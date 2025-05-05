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

 # ── STEP 2: Extract tracks + corrections in one pass via GPT ──
    st.info("Step 2: Extracting tracks and corrections via GPT…")
    client = OpenAI(api_key=api_key)

    system_prompt = """
You are a world‑class DJ‑set tracklist curator with a complete music knowledge base.
Given a list of raw YouTube comment texts, do two things:
1) Extract all timestamped track mentions in the form:
   MM:SS Artist - Track Title (optional remix/version and [label])
2) Extract any correction/update comments where a user writes something like
   "edit:", "correction:", "update:", "oops:", etc., that clarifies or replaces
   a previous track.

Return **only** a JSON object with two keys:
- "tracks": a list of objects for the original timestamped mentions,
- "corrections": a list of objects for the correction lines.

Each object must have exactly these fields:
  • artist  (string)
  • track   (string)
  • version (string, or empty if none)
  • label   (string, or empty if none)

No extra keys, no prose.
"""

    few_shot = """
### Example Input:
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
07:20 Cormac - Sparks
10:00 edit: John Noseda - Climax (VIP Mix)

### Example JSON Output:
{
  "tracks": [
    {"artist":"John Noseda","track":"Climax","version":"","label":""},
    {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"},
    {"artist":"Cormac","track":"Sparks","version":"","label":""}
  ],
  "corrections": [
    {"artist":"John Noseda","track":"Climax","version":"VIP Mix","label":""}
  ]
}
"""

    # bundle up to first 100 comments
    snippet = "\n".join(comments[:100])
    st.text_area("❯ Prompt sent to GPT (first 100 comments):", snippet, height=200)

    def extract_json(raw: str) -> str:
        # remove code fences if any
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def ask(model_name: str) -> dict:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"assistant", "content":few_shot},
                {"role":"user",      "content":f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    tracks = []
    corrections = []
    used_model = None

    for m in [model_choice, "gpt-3.5-turbo"]:
        try:
            raw = ask(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if (
                isinstance(parsed, dict)
                and "tracks" in parsed
                and "corrections" in parsed
            ):
                tracks      = parsed["tracks"]
                corrections = parsed["corrections"]
                used_model  = m
                break
        except Exception:
            continue

    if used_model is None:
        st.error("❌ GPT failed to extract any tracks or corrections.")
        st.stop()

    # merge original tracks + corrections (you can dedupe if desired)
    all_entries = tracks + corrections

    st.success(f"✅ {len(tracks)} tracks + {len(corrections)} corrections identified via {used_model}.")

    # display numbered list
    for i, t in enumerate(all_entries, start=1):
        artist  = t.get("artist", "Unknown Artist")
        track   = t.get("track",  "Unknown Track")
        version = t.get("version","")
        label   = t.get("label",  "")
        line = f"{i}. {artist} - {track}"
        if version:
            line += f" ({version})"
        if label:
            line += f" [{label}]"
        st.write(line)
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
