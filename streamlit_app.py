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

 # ── STEP 2: Rich GPT‑4 extraction with dual examples ──
    st.info("Step 2: Extracting track names via GPT with enriched few‑shot examples…")
    client = OpenAI(api_key=api_key)

    # System instructions
    system_prompt = """
You are a world‑class DJ‑set tracklist curator.  Given timestamped comment snippets, extract the
full, ordered tracklist.  Enrich each entry by filling in missing pieces (version, label) when possible.
Return **ONLY** a JSON array of objects with keys:
  • artist  (string)
  • track   (string)
  • version (string, or empty if none)
  • label   (string, or empty if none)
No extra keys, no commentary.
"""

    # Two few‑shot examples drawn from real comments
    few_shot_example = """
### Example 1 (sparse comments):
Comments:
03:45 John Noseda - Climax
05:10 Roy - Shooting Star [1987]
07:20 Cormac - Sparks

### JSON output:
[
  {"artist":"John Noseda","track":"Climax","version":"","label":""},
  {"artist":"Roy","track":"Shooting Star","version":"","label":"1987"},
  {"artist":"Cormac","track":"Sparks","version":"","label":""}
]

### Example 2 (detailed comment):
Comments:
00:00 Sylvester - I need you (extended 12\" mix)
05:00 Le Jete - La cage aux folles
07:10 Divine - Love Reaction
10:40 Claudja Barry - Work me over
12:10 Club Domani & Airys - A che ora l'amora (Hifi Sean mix)
15:50 ? - ?
18:00 Soft Cell - Tainted Love
22:30 ? - ?
25:00 Ascii Disko - Einfach
27:50 KiNK - Clap on 2
31:00 Vincent Palacino - Hard diversion
32:20 Fierce Ruling Diva - Rub It In
34:35 Glam - Hell's Party (DJ Ricci & DFC team mix)
37:10 Digital Domain - I Need Relief (1992)
40:30 Terrorize - It's Just a Feeling
43:30 Cinthie - City Lights
47:25 Sterling Void - It's Alright 98 Re‑Edit

### JSON output:
[
  {"artist":"Sylvester","track":"I need you","version":"extended 12\\\" mix","label":""},
  {"artist":"Le Jete","track":"La cage aux folles","version":"","label":""},
  {"artist":"Divine","track":"Love Reaction","version":"","label":""},
  {"artist":"Claudja Barry","track":"Work me over","version":"","label":""},
  {"artist":"Club Domani & Airys","track":"A che ora l'amora","version":"Hifi Sean mix","label":""},
  {"artist":"Soft Cell","track":"Tainted Love","version":"","label":""},
  {"artist":"Ascii Disko","track":"Einfach","version":"","label":""},
  {"artist":"KiNK","track":"Clap on 2","version":"","label":""},
  {"artist":"Vincent Palacino","track":"Hard diversion","version":"","label":""},
  {"artist":"Fierce Ruling Diva","track":"Rub It In","version":"","label":""},
  {"artist":"Glam","track":"Hell's Party","version":"DJ Ricci & DFC team mix","label":""},
  {"artist":"Digital Domain","track":"I Need Relief","version":"","label":"1992"},
  {"artist":"Terrorize","track":"It's Just a Feeling","version":"","label":""},
  {"artist":"Cinthie","track":"City Lights","version":"","label":""},
  {"artist":"Sterling Void","track":"It's Alright","version":"98 Re‑Edit","label":""}
]
"""

    # Prepare the actual comments snippet
    snippet = "\n".join(comments[:50])
    st.text_area("❯ Prompt sent to GPT:", snippet, height=200)

    # Helper to strip markdown fences
    def extract_json(raw: str) -> str:
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    # Send to model
    def ask(model_name: str) -> str:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"assistant", "content":few_shot_example},
                {"role":"user",      "content":f"Comments:\n{snippet}"},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    # Try GPT-4, fallback to 3.5
    tracks = None
    used_model = None
    for m in [model_choice, "gpt-3.5-turbo"]:
        try:
            raw = ask(m)
            clean = extract_json(raw)
            parsed = json.loads(clean)
            if isinstance(parsed, list) and parsed:
                tracks = parsed
                used_model = m
                break
        except Exception:
            continue

    if not tracks:
        st.error("❌ GPT failed to extract any tracks.")
        st.stop()

    st.success(f"✅ {len(tracks)} tracks identified and enriched via {used_model}.")
    for i, t in enumerate(tracks, start=1):
        artist  = t.get("artist","Unknown Artist")
        track   = t.get("track","Unknown Track")
        version = t.get("version","")
        label   = t.get("label","")
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
