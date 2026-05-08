import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext  # חשוב לאיפוס מצבים
from bot.models.database import SessionLocal, User, init_db

# === תוספת: ייבוא הסקדיולר וקובץ הדשבורד החדש ===
from bot.utils.scheduler import start_scheduler
from bot.handlers import deliveries, rides, bidding, driver_reg, admin_panel, driver_actions, client_actions, driver_management, driver_dashboard
# ===============================================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# רישום הראוטרים
dp.include_router(deliveries.router)
dp.include_router(rides.router)
dp.include_router(driver_actions.router)
dp.include_router(driver_reg.router)   # שאלון הרישום החדש
dp.include_router(admin_panel.router)  # לוח האישורים של המנהל
dp.include_router(client_actions.router)     # מסך ההזמנות שלי (לקוח)
dp.include_router(driver_management.router)  # מסך ניהול עבודות ישן (אם ישארו שם פונקציות)
dp.include_router(driver_dashboard.router)   # --- תוספת: מסך הניהול החדש והרווחים ---
dp.include_router(bidding.router)      # מנוע המכרז (בסוף כי הוא מטפל ב-callbacks)

def get_keyboard(user: User):
    """בונה את התפריט הדינמי לפי תפקיד המשתמש והמצב הנוכחי שלו"""
    kb = []
    
    if user.current_mode == "client":
        # תפריט לקוח
        kb.append([types.KeyboardButton(text="🚖 הזמנת נסיעה"), types.KeyboardButton(text="📦 שליחת חבילה")])
        
        # כפתור ניהול ההזמנות של הלקוח
        kb.append([types.KeyboardButton(text="📋 ההזמנות שלי")])
        
        # כפתור מעבר/רישום
        if user.role == "driver":
            kb.append([types.KeyboardButton(text="🔄 עבור למסך נהג")])
        else:
            kb.append([types.KeyboardButton(text="🆔 הרשמה כנהג/שליח")])
            
    elif user.current_mode == "driver": 
        # תפריט נהג 
        status_btn = "🔴 התנתק (כרגע מחובר)" if user.is_available else "🟢 התחבר (כרגע מנותק)"
        kb.append([types.KeyboardButton(text=status_btn)])
        
        # --- תוספת: כפתורי הדשבורד החדשים (מחליף את הפיצול הישן) ---
        kb.append([types.KeyboardButton(text="📅 העבודות שלי (פעיל)")])
        kb.append([types.KeyboardButton(text="📊 דשבורד ורווחים")])
        # -------------------------------------------------------
        
        kb.append([types.KeyboardButton(text="📍 שנה אזור עבודה")])
        kb.append([types.KeyboardButton(text="🔄 עבור למסך לקוח")])
        
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """פקודת התחלה - מאפסת מצבים קודמים ומציגה תפריט ראשי"""
    await state.clear()  # פותר את הבעיה של מצבים "תקועים"
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        # משתמש חדש
        user = User(
            telegram_id=message.from_user.id, 
            role="client", 
            current_mode="client"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # הבדיקה החדשה: אם הוא נהג ומצב העבודה שלו הוא נהג - הצג לו את הדשבורד
    markup = get_keyboard(user)
    
    welcome_text = f"שלום {message.from_user.first_name}! 👋\n"
    if user.role == "driver" and user.current_mode == "driver":
        welcome_text += "חזרת למסך הנהג. העבודות שלך מחכות לך למטה! 👇"
    else:
        welcome_text += "ברוך הבא למערכת.\nמה ברצונך לעשות?"

    db.close()
    
    await message.answer(welcome_text, reply_markup=markup)

@dp.message(F.text == "🔄 עבור למסך נהג")
async def switch_to_driver(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user and user.role == "driver":
        if not user.is_verified:
            await message.answer("⚠️ החשבון שלך עדיין ממתין לאישור מנהל. תקבל הודעה ברגע שתאושר.")
        else:
            user.current_mode = "driver"
            db.commit()
            markup = get_keyboard(user)
            await message.answer("🛠️ עברת למצב נהג. כאן תקבל התראות על עבודות חדשות.", reply_markup=markup)
    else:
        await message.answer("עוד לא נרשמת כנהג. לחץ על 'הרשמה כנהג/שליח' כדי להתחיל.")
    
    db.close()

@dp.message(F.text == "🔄 עבור למסך לקוח")
async def switch_to_client(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user:
        user.current_mode = "client"
        db.commit()
        markup = get_keyboard(user)
        await message.answer("👤 עברת למסך לקוח. נסיעה טובה!", reply_markup=markup)
    
    db.close()

# --- תוספת קטנה של באג פיקס: התאמנו את הטקסטים שהבוט מחפש לטקסטים שרשומים על הכפתור! ---
@dp.message(F.text.in_(["🟢 התחבר (כרגע מנותק)", "🔴 התנתק (כרגע מחובר)"]))
async def toggle_driver_availability(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user and user.role == "driver":
        user.is_available = not user.is_available
        db.commit()
        status_str = "מחובר 🟢" if user.is_available else "מנותק 🔴"
        markup = get_keyboard(user)
        await message.answer(f"הסטטוס שלך עודכן ל: **{status_str}**", reply_markup=markup)
    
    db.close()

async def main():
    # יצירת טבלאות
    init_db()
    
    # --- תוספת: הפעלת משימות הרקע (הסקדיולר) ---
    start_scheduler(bot)
    # ---------------------------------------
    
    # ניקוי עדכונים קודמים והרצה
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Bot is running and waiting for orders...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
