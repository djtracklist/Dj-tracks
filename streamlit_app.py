
import openai

# Set up OpenAI API key
api_key = 'your-api-key'  # Make sure to replace with your actual API key

# Input: YouTube comments (example provided)
comments_text = """ 
Replace this with the YouTube comments you want to analyze.
"""

# Craft the prompt to extract track and artist names
prompt = f"""
Extract any track names and artists mentioned, and return them as a list.
Be flexible with format, and include entries like:
'Track: "Ecstasy Surrounds Me", Artist: "Artist Name"'
"""

# Make the OpenAI API call to extract tracks
try:
    response = openai.ChatCompletion.create(
        model="gpt-4", 
        messages=[{"role": "user", "content": prompt + comments_text}], 
        api_key=api_key
    )
    
    # Handle and display the response from OpenAI
    extracted_tracks = response['choices'][0]['message']['content']
    print("Extracted tracks and artists:")
    print(extracted_tracks)

except Exception as e:
    print(f"An error occurred: {e}")
