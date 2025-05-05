import os
import streamlit as st
import yt_dlp
import openai
import json

# ── SIDEBAR (no more "Enable MP3 download" toggle) ──
st.sidebar.title("Options")
model = st.sidebar.selectbox("Choose OpenAI model:", ["gpt-4", "gpt-3.5-turbo"])
api_key = st.sidebar.text_input("OpenAI API Key:", type="password")
max_comments = st.sidebar.number_input("Max comments to fetch:", min_value=1, max_value=500, value=100)
sort_by = st.sidebar.selectbox("Sort comments by:", ["recent", "popular"])

openai.api_key = api_key

# ── MAIN APP ──
st.title("DJ Set Track Extractor + MP3 Downloader")

url = st.text_input("YouTube DJ Set URL:")
if not url:
    st.stop()

if st.button("Extract Tracks"):
    # STEP 1: download comments
    st.info("Step 1: Downloading YouTube comments…")
    cmd = [
        "youtube-comment-downloader",
        "--url", url,
        "--limit", str(max_comments),
        "--sort", sort_by
    ]
    try:
        result = os.popen(" ".join(cmd)).read()
        comments = json.loads(result)
        st.success(f"{len(comments)} comments downloaded.")
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        st.stop()

    # STEP 2: extract tracks via GPT
    st.info("Step 2: Extracting track names via GPT…")
    comment_block = "\n".join(c.get("text", "") for c in comments)
    system_prompt = (
        "You are a DJ‑set tracklist expert. "
        "Extract any track names and artists mentioned, including versions/remixes, "
        "and return them as a JSON list of objects with `artist` and `track` fields."
    )
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": comment_block}
            ],
            temperature=0
        )
        raw = response["choices"][0]["message"]["content"]
        tracks = json.loads(raw)
        st.success("✅ Tracks identified via " + model)
    except Exception as e:
        st.error(f"Failed to extract tracks: {e}")
        st.stop()

    if not isinstance(tracks, list) or not tracks:
        st.error("No tracks found.")
        st.stop()

    # STEP 3: display & user‑driven MP3 download
    st.write("---")
    st.write("### Select tracks to download")

    labels = [
        f"{t.get('artist','Unknown Artist')} – {t.get('track','Unknown Track')}"
        for t in tracks
    ]

    selected = []
    for idx, label in enumerate(labels):
        if st.checkbox(label, value=True, key=f"trk_{idx}"):
            selected.append(label)

    if selected:
        if st.button("Download Selected MP3s"):
            st.info("📥 Downloading selected tracks…")
            os.makedirs("downloads", exist_ok=True)
            downloaded = []

            for label in selected:
                st.write(f"▶️ Downloading {label}")
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join("downloads","%(title)s.%(ext)s"),
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"ytsearch1:{label}", download=True)
                        path = ydl.prepare_filename(info)
                        downloaded.append(path)
                    st.success(f"✅ {os.path.basename(path)}")
                except Exception as e:
                    st.error(f"❌ Failed to download {label}: {e}")

            # ZIP & download
            import io, zipfile
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for p in downloaded:
                    zf.write(p, arcname=os.path.basename(p))
            zip_buf.seek(0)

            st.download_button(
                "Download All as ZIP",
                data=zip_buf,
                file_name="dj_tracks.zip",
                mime="application/zip",
            )
    else:
        st.info("Select one or more tracks above to enable downloading.")
