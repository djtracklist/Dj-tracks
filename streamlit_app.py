import os
import json
import streamlit as st
import yt_dlp
import openai
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT, SORT_BY_POPULAR

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="wide")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# --- Inputs ---
url          = st.text_input("YouTube DJ Set URL")
model_choice = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.text_input("Enter your OpenAI API Key:", type="password")
enable_dl    = st.checkbox("Enable MP3 download")

if st.button("Extract Tracks & Download"):
    if not url or not api_key:
        st.error("Please provide both the YouTube URL and your OpenAI API key.")
        st.stop()

    # Step 1: Download comments via Python API (no CLI)
    st.info("Step 1: Downloading comments…")
    try:
        ycd = YoutubeCommentDownloader()
        # choose sort constant if you need popular vs recent
        sort_flag = SORT_BY_RECENT
        comments = []
        for c in ycd.get_comments_from_url(url, sort_by=sort_flag):
            text = c.get("text", "").strip()
            if text:
                comments.append(text)
            if len(comments) >= 100:
                break
        if not comments:
            raise RuntimeError("No comments fetched.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Few‑shot GPT extraction
    st.info("Step 2: Extracting track names via GPT…")
    openai.api_key = api_key

    snippet = "\n".join(comments[:50])
    system_prompt = (
        "You are an expert at reading DJ-set tracklists from YouTube comments and replying with pure JSON."
    )
    few_shot = (
        "Example input:\n"
        "Comments:\n"
        "12:34 Floating Points – Birth 4000\n"
        "22:10 Tiga & Hudson Mohawke – Untitled Codename Rimini\n\n"
        "Example output (JSON only):\n"
        "[\n"
        "  {\"artist\":\"Floating Points\",\"track\":\"Birth 4000\"},\n"
        "  {\"artist\":\"Tiga & Hudson Mohawke\",\"track\":\"Untitled Codename Rimini\"}\n"
        "]"
    )
    user_block = f"Comments:\n{snippet}"

    def clean(raw: str) -> str:
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def ask(model: str) -> str:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"assistant", "content":few_shot},
                {"role":"user",      "content":user_block},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content

    raw = ask(model_choice)
    cleaned = clean(raw)
    try:
        tracks = json.loads(cleaned)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError
        st.success(f"✅ {len(tracks)} tracks identified via {model_choice}.")
    except:
        if model_choice == "gpt-4":
            st.warning("GPT-4 output invalid, retrying with gpt-3.5-turbo…")
            raw = ask("gpt-3.5-turbo")
            cleaned = clean(raw)
            try:
                tracks = json.loads(cleaned)
                st.success("✅ Tracks identified via gpt-3.5-turbo.")
            except Exception as e:
                st.error(f"Both models failed: {e}")
                st.stop()
        else:
            st.error("Failed to parse GPT output.")
            st.stop()

    # Step 3: UI & Download
    st.write("---")
    st.write("### Select tracks to download")
    labels = [f"{t['artist']} - {t['track']}" for t in tracks]
    selected = st.multiselect("Choose tracks:", options=labels, default=labels)

    if enable_dl and selected:
        st.info("Step 3: Downloading MP3s…")
        os.makedirs("downloads", exist_ok=True)
        ydl_opts = {
            "format":"bestaudio/best",
            "outtmpl": os.path.join("downloads","%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for q in selected:
                st.write(f"▶️ {q}")
                try:
                    ydl.download([f"ytsearch1:{q}"])
                    st.write("Done")
                except Exception as dl_err:
                    st.error(f"Failed: {dl_err}")
        st.success("🎉 All selected tracks saved to `downloads/`.")
    elif enable_dl:
        st.warning("No tracks selected.")
