import requests
import os
# We import set_key to write to the file automatically
from dotenv import load_dotenv, set_key 

load_dotenv()

client_id = os.getenv("SOUNDCLOUD_CLIENT_ID")
client_secret = os.getenv("SOUNDCLOUD_CLIENT_SECRET")

# IMPORTANT: Ensure this matches your SoundCloud Dashboard
redirect_uri = "http://localhost:8000/callback" 

def step_1_get_auth_url():
    print("--- STEP 1: AUTHORIZE ---")
    url = f"https://secure.soundcloud.com/connect?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}"
    
    print(f"1. Open this URL in an **INCOGNITO** browser window:\n")
    print(f"{url}\n")
    print("2. Log in and click 'Connect'.")
    print("3. You will see a 'This site can't be reached' page.")
    print("4. Copy the code from the URL bar (everything after 'code=').")
    
    code = input("\n> Paste the 'code' part here: ").strip()
    return code

def step_2_exchange_code(auth_code):
    print("\n--- STEP 2: EXCHANGE CODE FOR TOKENS ---")
    url = "https://secure.soundcloud.com/oauth/token"
    
    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": auth_code
    }
    
    headers = {"accept": "application/json; charset=utf-8"}
    
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        
        # --- AUTOMATION SECTION ---
        # This writes the new tokens directly to your .env file
        print("\nSUCCESS! Saving tokens to .env file...")
        
        set_key(".env", "SOUNDCLOUD_ACCESS_TOKEN", data['access_token'])
        set_key(".env", "SOUNDCLOUD_REFRESH_TOKEN", data['refresh_token'])
        
        print("Done. Your .env file is updated.")
        # --------------------------
        
    else:
        print(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    if not client_id or not client_secret:
        print("Error: Missing Client ID or Secret in .env file.")
    else:
        code = step_1_get_auth_url()
        if code:
            step_2_exchange_code(code)