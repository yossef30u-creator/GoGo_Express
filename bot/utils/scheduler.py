import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
# --- תוספת: ייבוא User כדי לבדוק נהגים ---
from bot.models.database import SessionLocal, Job, User
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- תוספת: הגדרת אזור זמן ידנית כדי למנוע קריסה ב-Termux ---
try:
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
except Exception:
    import datetime as dt_module
    tz = dt_module.timezone.utc
# -------------------------------------------------------------

# הוספנו את ה-timezone לכאן
scheduler = AsyncIOScheduler(timezone=tz)

async def check_pending_jobs(bot: Bot):
    db = SessionLocal()
    # חובה להשתמש ב-utcnow כדי להיות מסונכרנים עם ה-Database שלנו
    now = datetime.utcnow()
    
    # ==========================================
    # 1. ניקוי עמוק: ביטול אוטומטי אחרי 30 דקות
    # ==========================================
    dead_jobs = db.query(Job).filter(
        Job.status.in_(["open", "pending_decision"]),
        Job.created_at <= now - timedelta(minutes=30)
    ).all()

    for job in dead_jobs:
        job.status = "cancelled"
        db.commit()
        
        service_name = "הנסיעה" if job.type == "ride" else "המשלוח"
        try:
            await bot.send_message(
                job.client_id,
                f"⚠️ **{service_name} בוטלה אוטומטית (עברה חצי שעה)**\n\n"
                f"חלף זמן רב ולא נמצא מענה לעבודה #{job.id}, לכן היא בוטלה במערכת.\n"
                f"נשמח לעמוד לשירותך שוב בהמשך!"
            )
        except Exception as e:
            logging.error(f"Failed to send 30m auto-cancel to client {job.client_id}: {e}")

    # ==========================================
    # 2. התראת עיכוב: הצעת העלאת מחיר אחרי 15 דקות
    # ==========================================
    # מושכים רק עבודות שפתוחות בדיוק בין 15 ל-30 דקות
    expired_jobs = db.query(Job).filter(
        Job.status == "open",
        Job.created_at <= now - timedelta(minutes=15)
    ).all()

    for job in expired_jobs:
        if job.type == "ride":
            service_name = "נסיעה"
            provider_name = "נהג"
            icon = "🚖"
        else:
            service_name = "משלוח"
            provider_name = "שליח"
            icon = "📦"

        try:
            kb = InlineKeyboardBuilder()
            kb.button(text="💰 העלאת מחיר (ב-10 ₪)", callback_data=f"raise_price_{job.id}")
            kb.button(text="❌ ביטול הזמנה", callback_data=f"ask_cancel_{job.id}") # מפנה ל-Handler הקיים של ביטול לקוח
            
            await bot.send_message(
                job.client_id,
                f"⏰ {icon} **עדכון על ה{service_name} שלך (#{job.id}):**\n\n"
                f"עברו 15 דקות וטרם נמצא {provider_name} פנוי.\n"
                f"המערכת עדיין מנסה לאתר עבורך מענה.\n\n"
                f"האם תרצה להעלות את המחיר כדי לזרז את המציאה, או לבטל את הבקשה?",
                reply_markup=kb.as_markup()
            )
            
            # מעדכנים סטטוס כדי שהסקדיולר לא יציק לו שוב בדקה הבאה
            job.status = "pending_decision"
            db.commit()
            
        except Exception as e:
            logging.error(f"Error notifying client about expired {job.type}: {e}")

    db.close()


# ==========================================
# 3. תוספת: בדיקת תוקף מסמכי נהגים (פעם ביום)
# ==========================================
async def check_driver_documents(bot: Bot):
    db = SessionLocal()
    today = datetime.utcnow().date()
    warning_limit = today + timedelta(days=30)
    
    # בודק רק נהגים פעילים
    active_drivers = db.query(User).filter(
        User.role == "driver",
        User.is_active == True
    ).all()
    
    for driver in active_drivers:
        lic_exp = driver.license_expiry
        ins_exp = driver.insurance_expiry
        
        is_expired = False
        is_warning = False
        min_days_left = 9999
        
        # בדיקת רישיון
        if lic_exp:
            if lic_exp < today:
                is_expired = True
            elif lic_exp <= warning_limit:
                is_warning = True
                min_days_left = min(min_days_left, (lic_exp - today).days)
                
        # בדיקת ביטוח
        if ins_exp:
            if ins_exp < today:
                is_expired = True
            elif ins_exp <= warning_limit:
                is_warning = True
                min_days_left = min(min_days_left, (ins_exp - today).days)
                
        try:
            if is_expired:
                # הנהג נחסם - מעדכנים במסד הנתונים
                driver.is_active = False
                driver.is_available = False # מנתק אותו מקבלת עבודות
                db.commit()
                
                await bot.send_message(
                    driver.telegram_id,
                    "⛔ **חשבונך הושעה אוטומטית!**\n"
                    "תוקף רישיון הנהיגה או הביטוח שלך פג. לא תוכל לקבל הצעות עבודה עד שתעלה מסמכים מעודכנים לאישור מנהל."
                )
            elif is_warning:
                # אזהרה יומית במהלך 30 הימים האחרונים
                await bot.send_message(
                    driver.telegram_id,
                    f"⚠️ **התראת מסמכים חשובה!**\n"
                    f"אחד מהמסמכים שלך עומד לפוג בעוד **{min_days_left} ימים**.\n"
                    f"אנא דאג לחדש אותו ולהעלות למערכת כדי למנוע את חסימת חשבונך."
                )
        except Exception as e:
            logging.error(f"Failed to notify driver {driver.telegram_id} about docs: {e}")
            
    db.close()


def start_scheduler(bot: Bot):
    # הפעלת הסקדיולר לבדיקה מחזורית כל דקה (לעבודות)
    scheduler.add_job(check_pending_jobs, "interval", minutes=1, args=[bot])
    
    # --- תוספת: הפעלת בדיקת מסמכים פעם ביום בשעה 10:00 בבוקר ---
    scheduler.add_job(check_driver_documents, "cron", hour=10, minute=0, args=[bot])
    
    scheduler.start()
