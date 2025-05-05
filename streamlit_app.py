import streamlit as st
import json
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT
import openai
import yt_dlp

st.set_page_config(page_title="DJ Set Tracklist & MP3 Downloader")
st.title("🎧 DJ Set Tracklist & MP3 Downloader")

# --- Inputs ---
url = st.text_input("Enter YouTube DJ Set URL:")
model = st.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

if st.button("Extract Tracklist"):
    if not url or not api_key:
        st.error("Please provide both the YouTube URL and your OpenAI API key.")
        st.stop()

    openai.api_key = api_key

    # Step 1: download comments
    st.info("Step 1: Downloading YouTube comments...")
    downloader = YoutubeCommentDownloader()
    try:
        raw_comments = list(
            downloader.get_comments_from_url(
                url,
                sort_by=SORT_BY_RECENT,
                max_comments=100
            )
        )
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    st.success(f"✅ {len(raw_comments)} comments downloaded.")

    # extract text and take first 50 for prompt
    comments = [c["text"] for c in raw_comments]
    comments_block = "\n".join(comments[:50])

    # Step 2: call GPT
    st.info("Step 2: Extracting track names using GPT...")
    prompt = (
        "You are an expert at identifying tracklists from DJ set comments.\n"
        "Extract any track names and artists mentioned in the following comments.\n"
        "Return ONLY a JSON array of objects, each with 'artist' and 'track' fields.\n"
        "Do not include any extra explanation.\n\n"
        f"Comments:\n{comments_block}"
    )

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        gpt_output = response.choices[0].message.content.strip()
        tracklist = json.loads(gpt_output)
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    if not isinstance(tracklist, list) or not tracklist:
        st.warning("No tracks were identified by GPT.")
        st.stop()

    # pretty‐print JSON raw
    with st.expander("Raw GPT output"):
        st.code(json.dumps(tracklist, indent=2), language="json")

    # Step 3: let user pick & download
    st.success("✅ Tracks identified:")
    options = [f"{t['artist']} - {t['track']}" for t in tracklist]
    selected = st.multiselect("Select tracks to download:", options, default=options)

    if selected and st.button("Download Selected MP3s"):
        st.info("Step 3: Downloading MP3s…")
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            ],
            "outtmpl": "%(title)s.%(ext)s",
            "quiet": True,
        }

        for sel in selected:
            artist, track = sel.split(" - ", 1)
            query = f"ytsearch1:{artist} {track}"
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([query])
                st.success(f"Downloaded: {sel}")
            except Exception as e:
                st.error(f"Failed to download {sel}: {e}")
