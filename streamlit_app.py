import os
import json
import subprocess
import streamlit as st
import openai
import yt_dlp

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="wide")
st.title("YouTube DJ Set Tracklist Extractor & MP3 Downloader")

# --- Inputs ---
url          = st.text_input("YouTube DJ Set URL")
model_choice = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.text_input("Enter your OpenAI API Key:", type="password")
enable_dl    = st.checkbox("Enable MP3 download")

if st.button("Extract Tracks & Download MP3s"):
    # 1) Validate
    if not url or not api_key:
        st.error("Please provide both a YouTube URL and your OpenAI API key.")
        st.stop()

    # 2) Download comments (unchanged)
    st.info("Step 1: Downloading comments…")
    try:
        result = subprocess.run(
            ["youtube-comment-downloader", "--url", url, "--sort", "0", "--limit", "100"],
            capture_output=True, text=True, check=True
        )
        comments = json.loads(result.stdout)
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # 3) Few‑shot GPT extraction
    st.info("Step 2: Extracting track names via GPT…")
    openai.api_key = api_key

    snippet = "\n".join(c.get("text","") for c in comments[:50])

    system_prompt = (
        "You are an expert at reading DJ-set tracklists from YouTube comments "
        "and replying with pure JSON."
    )
    few_shot_example = (
        "Example input:\n"
        "Comments:\n"
        "12:34 Floating Points – Birth 4000\n"
        "22:10 Tiga & Hudson Mohawke – Untitled Codename Rimini\n"
        "30:45 Decius – Hashtag Booty Finger [Decius Trax]\n\n"
        "Example output (JSON only):\n"
        "[\n"
        "  {\"artist\":\"Floating Points\",\"track\":\"Birth 4000\"},\n"
        "  {\"artist\":\"Tiga & Hudson Mohawke\",\"track\":\"Untitled Codename Rimini\"},\n"
        "  {\"artist\":\"Decius\",\"track\":\"Hashtag Booty Finger [Decius Trax]\"}\n"
        "]"
    )
    user_block = f"Comments:\n{snippet}"

    def clean_json(raw: str) -> str:
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def call_model(name: str) -> str:
        resp = openai.ChatCompletion.create(
            model=name,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"assistant", "content":few_shot_example},
                {"role":"user",      "content":user_block},
            ],
            temperature=0
        )
        return resp.choices[0].message.content

    # Try primary model, then fallback
    raw_output = call_model(model_choice)
    cleaned = clean_json(raw_output)
    try:
        tracks = json.loads(cleaned)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Empty or invalid list")
        st.success(f"✅ {len(tracks)} tracks identified via {model_choice}.")
    except Exception:
        if model_choice == "gpt-4":
            st.warning("GPT-4 failed to produce valid JSON — retrying with gpt-3.5-turbo…")
            raw_output = call_model("gpt-3.5-turbo")
            cleaned = clean_json(raw_output)
            try:
                tracks = json.loads(cleaned)
                if not isinstance(tracks, list) or not tracks:
                    raise ValueError
                st.success("✅ Tracks identified via gpt-3.5-turbo.")
            except Exception as err:
                st.error(f"Both models failed: {err}")
                st.stop()
        else:
            st.error("Failed to parse GPT output.")
            st.stop()

    # 4) Selection UI
    if not tracks:
        st.warning("No tracks extracted.")
        st.stop()

    st.write("---")
    st.write("### Select tracks to download")
    options = []
    for t in tracks:
        artist = t.get("artist", "Unknown Artist")
        title  = t.get("track",  "Unknown Track")
        options.append(f"{artist} - {title}")

    selected = st.multiselect("Choose tracks:", options, default=options)

    # 5) Download MP3s
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
            for query in selected:
                st.write(f"▶️ {query}")
                try:
                    ydl.download([f"ytsearch1:{query}"])
                    st.write("Done")
                except Exception as dl_err:
                    st.error(f"Failed: {dl_err}")
        st.success("🎉 All selected tracks saved to `downloads/`.")
    elif enable_dl:
        st.warning("No tracks selected for download.")
