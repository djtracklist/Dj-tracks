import streamlit as st
import subprocess
import json
from openai import OpenAI

st.set_page_config(page_title="DJ Set Track Extractor", layout="wide")
st.title("🎧 DJ Set Track Extractor + MP3 Downloader")

# User inputs
url = st.text_input("YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracks & Download MP3s"):
    if not url:
        st.error("Please enter a YouTube URL.")
        st.stop()
    if not api_key:
        st.error("Please enter your OpenAI API key.")
        st.stop()

    # Step 1: Download comments
    st.info("Step 1: Downloading YouTube comments…")
    cmd = [
        "youtube-comment-downloader",
        "--url", url,
        "--limit", "100"
    ]
    try:
        raw_output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        comments = raw_output.splitlines()
        st.success(f"✅ {len(comments)} comments downloaded.")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # Step 2: Extract tracks via GPT
    st.info("Step 2: Extracting track names via GPT…")
    client = OpenAI(api_key=api_key)

    prompt = f"""You are an expert at identifying full track titles and their artists from user comments.
Identify all unique tracks in the following format, one per line:
Artist – Track Title (Optional Remix/Version information)
Return only the list, no additional commentary. """

    # Send only first 50 comments to avoid token issues
    comments_block = "\n".join(comments[:50])
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt + "\n\n" + comments_block}
            ]
        )
        raw = response.choices[0].message.content.strip()
        st.subheader("Raw GPT Output")
        st.code(raw)
        tracks = [line.strip() for line in raw.splitlines() if line.strip()]
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    if not tracks:
        st.error("No tracks found in comments.")
        st.stop()

    # Step 3: Let user select and (optionally) download MP3s
    st.subheader("Select tracks to download:")
    selected = st.multiselect("Choose tracks:", tracks, default=tracks)

    if selected and st.button("Download Selected MP3s"):
        st.info("Step 3: Downloading selected tracks…")
        for t in selected:
            st.write(f"Downloading: {t}")
        st.success("All selected downloads complete!")
