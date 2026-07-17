from dataclasses import dataclass
import os

@dataclass
class Config:

    API_KEY = os.getenv("KITE_API_KEY","")

    API_SECRET = os.getenv("KITE_API_SECRET","")

    ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN","")

    DATABASE="nice.db"

    DASHBOARD_REFRESH_MS=100

    SYMBOLS=[
        "NIFTY 50",
        "SENSEX"
    ]
