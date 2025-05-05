import streamlit as st
import subprocess
import json
import openai
import yt_dlp

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="wide")
st.title("YouTube DJ Set Tracklist Extractor & MP3 Downloader")

# --- Inputs ---
url        = st.text_input("YouTube DJ Set URL")
model      = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key    = st.text_input("Enter your OpenAI API Key:", type="password")
download_mp3 = st.checkbox("Enable MP3 download")

# --- Step 1: Download comments (unchanged) ---
if st.button("Extract Tracks & Download MP3s"):
    if not url or not api_key:
        st.error("Please provide both a YouTube URL and your OpenAI API key.")
        st.stop()

    st.info("Step 1: Downloading YouTube comments…")
    try:
        # <<< This block is frozen exactly as your working version >>>
        result = subprocess.run(
            ["youtube-comment-downloader", "--url", url, "--sort", "0", "--limit", "100"],
            capture_output=True, text=True, check=True
        )
        comments = json.loads(result.stdout)
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # --- Step 2: Few-shot GPT extraction ---
    st.info("Step 2: Extracting track names via GPT…")
    openai.api_key = api_key
    # build snippet
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
    user_content = f"Comments:\n{snippet}"

    def extract_json(raw: str) -> str:
        # strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return raw.strip()

    def call_model(m: str) -> str:
        resp = openai.ChatCompletion.create(
            model=m,
            messages=[
                {"role":"system",   "content":system_prompt},
                {"role":"assistant","content":few_shot_example},
                {"role":"user",     "content":user_content},
            ],
            temperature=0
        )
        return resp.choices[0].message.content

    # try primary model, then fallback if empty/invalid
    raw = call_model(model)
    clean = extract_json(raw)
    try:
        tracks = json.loads(clean)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Empty or invalid list")
        st.success(f"✅ {len(tracks)} tracks identified via {model}.")
    except Exception:
        if model == "gpt-4":
            st.warning("GPT-4 returned invalid JSON—retrying with gpt-3.5-turbo…")
            raw = call_model("gpt-3.5-turbo")
            clean = extract_json(raw)
            try:
                tracks = json.loads(clean)
                if not isinstance(tracks, list) or not tracks:
                    raise ValueError
                st.success("✅ Tracks identified via gpt-3.5-turbo.")
            except Exception as e:
                st.error(f"Both models failed: {e}")
                st.stop()
        else:
            st.error("Failed to parse GPT output.")
            st.stop()

    # --- Step 3: UI for selection & download ---
    if not tracks:
        st.warning("No tracks extracted.")
        st.stop()

    st.write("---")
    st.write("### Select tracks to download")
    options = [
        f\"{t.get('artist','Unknown Artist')} — {t.get('track','Unknown Track')}\" 
        for t in tracks
    ]
    selected = st.multiselect("Choose tracks:", options, default=options)

    if download_mp3 and selected:
        st.info("Step 4: Downloading selected MP3s…")
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
                st.write(f"▶ {q}")
                try:
                    ydl.download([f"ytsearch1:{q}"])
                    st.write("Done")
                except Exception as e:
                    st.error(f"Failed: {e}")
        st.success("🎉 All selected tracks saved to `downloads/`.")
    elif download_mp3:
        st.warning("No tracks selected for download.")
