import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

request_token = input("Paste request_token: ").strip()

kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
session = kite.generate_session(
    request_token,
    api_secret=os.environ["KITE_API_SECRET"],
)

print("\nAccess token:")
print(session["access_token"])