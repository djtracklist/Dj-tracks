
import streamlit as st
import openai
from youtube_comment_downloader import YoutubeCommentDownloader
import yt_dlp as youtube_dl
import json
import os

# Function to download YouTube comments
def download_youtube_comments(video_url, num_comments=100):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True,
        'dump_single_json': True,
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(video_url, download=False)
        comments = result.get('comments', [])
        if len(comments) > num_comments:
            comments = comments[:num_comments]
        return comments

# Function to interact with OpenAI API and extract track information
def extract_tracks_with_gpt(comments):
    openai.api_key = st.secrets["openai_api_key"]
    
    comments_text = "
".join([comment['text'] for comment in comments])

    prompt = f'''
    Here is a list of YouTube comments. Extract any track names and artists mentioned, and return them as a list.
    Example format:
    "Track Name - Artist Name"
    
    Comments:
    {comments_text}
    
    Be flexible with format, and include entries like:
    "Ecstasy Surrounds Me" - Artist not mentioned
    "Untitled Codename Rimini = Night Is Not" from "L'Ecstasy, TURBO 229" - Artist not mentioned
    "Front 242" - Artist not mentioned
    "Miss Kittin" - Artist not mentioned
    "Opus III" - Artist not mentioned
    "Channel Tres" - Artist not mentioned
    "Erlend Oye's Fine day" - Artist not mentioned
    "Washing Up" - Artist not mentioned
    "Wordy Rappinghood" - Artist not mentioned
    "Feel The Rush" - Artist not mentioned
    "Fever Ray - Triangle Walks (Tiga's 1-2-3-4 Remix)"
    "Bugatti" - Artist not mentioned
    "Tiga & Hudson Mohawke - BUYBUYSELL"
    "FAXMAN" - Artist not mentioned
    "Fine day" - Artist not mentioned
    "ecstasy surround me" - Artist not mentioned
    '''

    response = openai.Completion.create(
        engine="gpt-4",
        prompt=prompt,
        max_tokens=1500,
        temperature=0.7
    )

    return response.choices[0].text.strip()

# Streamlit app code
st.title("DJ Set Track Extractor & MP3 Downloader")

video_url = st.text_input("Enter YouTube DJ Set URL:")

if video_url:
    st.write(f"Extracting tracks from: {video_url}")

    # Step 1: Download YouTube comments directly
    comments = download_youtube_comments(video_url)
    st.write(f"{len(comments)} comments downloaded.")
    
    # Step 2: Extract tracks using GPT
    st.write("Step 2: Extracting track names using GPT...")
    tracklist = extract_tracks_with_gpt(comments)
    
    if tracklist:
        st.subheader("Tracks Identified:")
        st.write(tracklist)
    else:
        st.write("No tracks were identified. Please try a different video.")
