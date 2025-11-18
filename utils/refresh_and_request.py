import os
import requests
from dotenv import load_dotenv, set_key
from datetime import datetime, timedelta

load_dotenv()  # Load environment variables from the .env file

# Retrieve tokens from the environment variables
client_id = os.getenv("SOUNDCLOUD_CLIENT_ID")
client_secret = os.getenv("SOUNDCLOUD_CLIENT_SECRET")
access_token = os.getenv("SOUNDCLOUD_ACCESS_TOKEN")
refresh_token = os.getenv("SOUNDCLOUD_REFRESH_TOKEN")

# Check if we need to refresh the token
def refresh_access_token():
    url = "https://secure.soundcloud.com/oauth/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "accept": "application/json; charset=utf-8"
    }
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post(url, headers=headers, data=payload)

    if response.status_code == 200:
        # Save new tokens
        new_token_data = response.json()
        new_access_token = new_token_data["access_token"]
        new_refresh_token = new_token_data.get("refresh_token", refresh_token)  # sometimes refresh token remains the same

        # Save tokens to .env file
        set_key(".env", "SOUNDCLOUD_ACCESS_TOKEN", new_access_token)
        set_key(".env", "SOUNDCLOUD_REFRESH_TOKEN", new_refresh_token)

        print("Access token refreshed successfully!")
        return new_access_token
    else:
        print(f"Error refreshing access token: {response.status_code} - {response.text}")
        return None

def make_api_request():
    # Check if we already have a valid access token
    if not access_token:
        print("Access token is missing!")
        return

    # Example of making an API request with the access token
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    params = {
        "q": "lofi",  # Search query
        "limit": 50,   # Number of results
        "offset": 0    # Pagination offset
    }

    url = "https://api.soundcloud.com/tracks"
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        tracks = response.json()
        print(f"Successfully fetched {len(tracks)} tracks for query 'lofi'.")
    else:
        print(f"Error: {response.status_code} - {response.text}")

access_token = refresh_access_token()

if access_token:
    make_api_request()
