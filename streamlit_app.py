import os, json
import streamlit as st
import yt_dlp
from youtube_comment_downloader.downloader import YoutubeCommentDownloader, SORT_BY_RECENT
import openai

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader", layout="wide")
st.title("🎧 DJ Set Tracklist Extractor & MP3 Downloader")

# Inputs
url          = st.text_input("YouTube DJ Set URL")
model_choice = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key      = st.text_input("Enter your OpenAI API Key:", type="password")
enable_dl    = st.checkbox("Enable MP3 download")

if st.button("Extract Tracks & Download"):
    if not url or not api_key:
        st.error("Provide both the YouTube URL and your OpenAI API key.")
        st.stop()

    # --- Step 1: Download comments (unchanged) ---
    st.info("Step 1: Downloading comments…")
    try:
        ycd = YoutubeCommentDownloader()
        comments = []
        for c in ycd.get_comments_from_url(url, sort_by=SORT_BY_RECENT):
            txt = c.get("text","").strip()
            if txt:
                comments.append(txt)
            if len(comments) >= 100:
                break
        if not comments:
            raise RuntimeError("No comments fetched.")
        st.success(f"✅ {len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # --- Step 2: Extract tracks via GPT ---
    st.info("Step 2: Extracting track names via GPT…")
    openai.api_key = api_key

    comment_block = "\n".join(comments[:50])
    system_prompt = (
        "You are an expert at extracting complete DJ set tracklists from raw YouTube comments. "
        "Comments may mention tracks in formats like:\n"
        "  • Artist - Track\n"
        "  • Artist – Track (Remix Name)\n"
        "  • Artist & Collaborator - Title [Label]\n"
        "Your job: find **all distinct songs**, including any remix/version info in parentheses or brackets, "
        "and output a **JSON array** of objects, each with exactly two keys: "
        "`\"artist\"` and `\"track\"`.\n"
        "Do not output any extra text—pure JSON only."
    )
    user_prompt = f"Comments:\n{comment_block}"

    def ask(model: str):
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role":"system",    "content":system_prompt},
                {"role":"user",      "content":user_prompt},
            ],
            temperature=0
        )
        return resp.choices[0].message.content.strip()

    raw = ask(model_choice)

    # strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]

    # try parsing
    try:
        tracks = json.loads(raw)
        if not isinstance(tracks, list) or not tracks:
            raise ValueError("Empty or non‑list JSON")
        st.success(f"✅ {len(tracks)} tracks identified via {model_choice}.")
    except Exception:
        if model_choice == "gpt-4":
            st.warning("GPT-4 output invalid JSON, retrying with gpt-3.5-turbo…")
            raw = ask("gpt-3.5-turbo")
            if raw.startswith("```"):
                raw = raw.split("```")[1]
            try:
                tracks = json.loads(raw)
                st.success("✅ Tracks identified via gpt-3.5-turbo.")
            except Exception as e:
                st.error(f"Both models failed to produce valid JSON: {e}")
                st.code(raw, language="json")
                st.stop()
        else:
            st.error("Failed to parse GPT output.")
            st.code(raw
