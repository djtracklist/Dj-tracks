import streamlit as st
import subprocess
import os
import json
import openai

def download_comments(video_url, limit=100):
    """Use the bundled youtube_comment_downloader to pull comments."""
    try:
        completed = subprocess.run(
            [
                "python3", "-m", "youtube_comment_downloader",
                "--url", video_url,
                "--limit", str(limit)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(completed.stdout)
        return [entry["text"] for entry in data]
    except Exception as e:
        st.error(f"Failed to download comments: {e}")
        return []

def extract_tracks(comments, model, api_key):
    """Send comments to OpenAI and parse back a JSON list of {artist,track}."""
    openai.api_key = api_key
    # we only send the first 50 comments to stay under context limits
    snippet = "\n".join(comments[:50])
    prompt = (
        "Extract any track names and artists mentioned, and return them as a JSON list of objects "
        "with keys 'artist' and 'track'. Be flexible with format, and include entries like:\n"
        '[{"artist":"Artist Name","track":"Track Title"}, ...]\n\n'
    )
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role":"system","content":"You are a helpful assistant."},
            {"role":"user","content": prompt + snippet}
        ]
    )
    content = resp.choices[0].message.content
    # try raw JSON parse, or slice out the JSON array
    try:
        return json.loads(content)
    except:
        start = content.find("[")
        end = content.rfind("]") + 1
        return json.loads(content[start:end])

def download_track(query, folder="downloads"):
    """Search YouTube via yt-dlp and extract to MP3."""
    os.makedirs(folder, exist_ok=True)
    try:
        subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--output", f"{folder}/%(title)s.%(ext)s",
                f"ytsearch1:{query}"
            ],
            check=True
        )
    except Exception as e:
        st.warning(f"Download failed for {query}: {e}")

def main():
    st.title("🎧 DJ Set Tracklist Extractor + MP3 Downloader")
    url = st.text_input("Enter YouTube URL of the DJ set")
    model = st.selectbox("Choose OpenAI model", ["gpt-4","gpt-3.5-turbo"])
    api_key = st.text_input("OpenAI API Key", type="password")

    if st.button("Extract Tracks & Download MP3s"):
        # Step 1
        st.info("Step 1: Downloading YouTube comments…")
        comments = download_comments(url, limit=100)
        if not comments:
            st.error("No comments fetched. Check the URL or try another video.")
            return
        st.success(f"{len(comments)} comments downloaded.")

        # Step 2
        st.info("Step 2: Extracting track names using GPT…")
        tracks = extract_tracks(comments, model, api_key)
        if not tracks:
            st.error("No tracks identified.")
            return
        st.success("Tracks identified:")

        # Display with checkboxes
        to_download = []
        for idx, entry in enumerate(tracks):
            artist = entry.get("artist", "Unknown Artist")
            track  = entry.get("track",  "Unknown Track")
            label  = f"{artist} — {track}"
            if st.checkbox(label, key=idx):
                to_download.append(label)

        # Step 3
        if to_download:
            st.info("Step 3: Downloading selected tracks…")
            for q in to_download:
                download_track(q)
            st.success("All selected tracks have been downloaded to the downloads/ folder.")
        else:
            st.warning("No tracks selected for download.")

if __name__ == "__main__":
    main()
