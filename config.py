import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
CHANNEL_ID = os.environ["CHANNEL_ID"]  # @handle או מספר שלילי

# אדמינים — רשימה של user_id מופרדים בפסיק
ADMIN_IDS_RAW = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()]

# כמה ימים בין פרסומים
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", "5"))

DB_NAME = "ai_tools_bot"
