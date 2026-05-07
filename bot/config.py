import os
from dotenv import load_dotenv

# טעינת משתנים מקובץ .env הנסתר
load_dotenv()

# שליפת הטוקן מהמערכת
BOT_TOKEN = os.getenv("BOT_TOKEN")

# נתיב למסד הנתונים
DATABASE_URL = "sqlite:///./bot/models/ride_bot.db"

# מנהלי מערכת
ADMIN_IDS = [552041081]
