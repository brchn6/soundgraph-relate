import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fetch the access token from the environment variable
access_token = os.getenv("SOUNDCLOUD_ACCESS_TOKEN")

# Check if the access token is available
if not access_token:
    raise ValueError("SOUNDCLOUD_ACCESS_TOKEN is missing. Please ensure the token is set in your .env file.")

# Set the headers for the API request
headers = {
    "Authorization": f"Bearer {access_token}",  # Use the token for authentication
}

# Define the search query and parameters
SAMPLE_QUERY = "lofi"
params = {
    "q": SAMPLE_QUERY,  # Search term
    "limit": 50,         # Limit the number of results
    "offset": 0          # Pagination offset (if applicable)
}

# SoundCloud API endpoint for track search
url = "https://api.soundcloud.com/tracks"

# Make the GET request
response = requests.get(url, headers=headers, params=params)

# Check the response status code
if response.status_code == 200:
    print(f"Successfully fetched {len(response.json())} tracks for query '{SAMPLE_QUERY}':")
    # Optionally, print the first track's title as a sample
    tracks = response.json()
    print(f"Example track: {tracks[0]['title']}")  # Print the title of the first track
else:
    print(f"Error during API request: {response.status_code} - {response.text}")
