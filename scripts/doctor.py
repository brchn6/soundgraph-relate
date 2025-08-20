import os
from dotenv import load_dotenv
load_dotenv()

print("Auth mode:", "OAuth (Bearer)" if os.getenv("SOUNDCLOUD_ACCESS_TOKEN") else "Public client_id")
print("SOUNDCLOUD_CLIENT_ID:", bool(os.getenv("SOUNDCLOUD_CLIENT_ID")))
print("SOUNDCLOUD_ACCESS_TOKEN:", bool(os.getenv("SOUNDCLOUD_ACCESS_TOKEN")))
print("SC_BASE_URL:", os.getenv("SC_BASE_URL", "https://api.soundcloud.com"))
