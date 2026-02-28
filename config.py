import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DEV_ID = os.getenv("DEV_ID")
MONGO_URL = os.getenv("MONGO_URL")
POSTGRE_URL = os.getenv("POSTGRE_URL")