
import streamlit as st
import openai
import requests
import yt_dlp
from youtube_comment_downloader import YoutubeCommentDownloader

# API Key entry field
api_key = st.text_input("Enter your OpenAI API Key:", type="password")
model = st.selectbox("Choose OpenAI model:", ["gpt-3.5", "gpt-4"])

# YouTube URL input
url = st.text_input("Enter YouTube DJ Set URL:")

# Function to extract tracklist from the comments
def extract_tracks_from_comments(comments):
    comments_text = " ".join(comments)  # Combine all comments into one text
    prompt = f"Extract any track names and artists mentioned, and return them as a list. Be flexible with format, and include entries like: 'Track Name - Artist'. 

 Comments: {comments_text}"
    
    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    
    tracklist = response['choices'][0]['message']['content']
    return tracklist

if url:
    # Download YouTube comments
    ydl_opts = {'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_id = info_dict['id']
    
    try:
        comment_downloader = YoutubeCommentDownloader()
        comments = comment_downloader.get_comments_from_url(url, limit=100)  # Adjust limit as needed
        if comments:
            tracklist = extract_tracks_from_comments(comments)
            st.subheader("Tracklist")
            st.text(tracklist)
        else:
            st.warning("No comments were downloaded. Please check the YouTube URL or try a different video.")
    
    except Exception as e:
        st.error(f"Failed to get comments: {str(e)}")
else:
    st.info("Enter a valid YouTube URL to begin.")
