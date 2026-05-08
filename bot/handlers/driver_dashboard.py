from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.models.database import SessionLocal, Job, JobHistory
from datetime import datetime, timedelta
import urllib.parse

router = Router()

# ==========================================
# 1. ניהול עבודות פעילות + ניווט אוטומטי (Waze)
# ==========================================
@router.message(F.text == "📅 העבודות שלי (פעיל)")
async def show_active_jobs(message: types.Message):
    db = SessionLocal()
    driver_id = message.from_user.id
    
    # שליפת עבודות פעילות (נסיעות ומשלוחים)
    active_jobs = db.query(Job).filter(
        Job.driver_id == driver_id,
        Job.status == "assigned"
    ).all()
    
    if not active_jobs:
        await message.answer("✅ אין לך עבודות פעילות כרגע. תוכל לנוח או לחכות לקריאות חדשות!")
        db.close()
        return

    await message.answer(f"🔎 יש לך {len(active_jobs)} עבודות שממתינות לביצוע:")

    for job in active_jobs:
        # יצירת לינקים ל-Waze (קידוד הכתובת ל-URL תקין)
        waze_pickup = f"https://waze.com/ul?q={urllib.parse.quote(job.pickup_loc)}"
        waze_dropoff = f"https://waze.com/ul?q={urllib.parse.quote(job.dropoff_loc)}"
        
        kb = InlineKeyboardBuilder()
        # שורת כפתורי ניווט
        kb.row(
            types.InlineKeyboardButton(text="📍 נווט לאיסוף", url=waze_pickup),
            types.InlineKeyboardButton(text="🏁 נווט ליעד", url=waze_dropoff)
        )
        # שורת פעולות
        kb.row(
            types.InlineKeyboardButton(text="✅ סיימתי עבודה", callback_data=f"finish_job_{job.id}"),
            types.InlineKeyboardButton(text="❌ ביטול חירום", callback_data=f"driver_cancel_{job.id}")
        )
        
        job_type = "🚖 נסיעה" if job.type == "ride" else "📦 משלוח"
        
        await message.answer(
            f"{job_type} **#{job.id}**\n"
            f"📍 **מאיפה:** {job.pickup_loc}\n"
            f"🏁 **לאן:** {job.dropoff_loc}\n"
            f"⏰ **זמן נדרש:** {job.pickup_time}\n"
            f"💰 **תשלום:** {job.price} ₪\n"
            f"📝 **הערות:** {job.notes if job.notes else 'אין'}",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
            disable_web_page_preview=True # מונע מהלינקים של וויז לייצר תצוגה מקדימה ענקית
        )
    db.close()

# ==========================================
# 2. דשבורד חכם: רווחים, סטטיסטיקה וסינון זמנים
# ==========================================
@router.message(F.text == "📊 דשבורד ורווחים")
async def show_dashboard_main(message: types.Message):
    # שולח את התצוגה הדיפולטיבית - "היום"
    await render_dashboard(message, period="today", is_edit=False)

# קבלת הלחיצות על כפתורי הסינון (היום/השבוע/החודש)
@router.callback_query(F.data.startswith("dash_filter_"))
async def update_dashboard_filter(callback: types.CallbackQuery):
    period = callback.data.split("_")[2]
    await render_dashboard(callback.message, period=period, is_edit=True, driver_id=callback.from_user.id)
    await callback.answer()

# פונקציה מרכזית שמייצרת את תצוגת הדשבורד (חוסך קוד כפול)
async def render_dashboard(message_or_callback: types.Message, period: str, is_edit: bool, driver_id: int = None):
    db = SessionLocal()
    user_id = driver_id if driver_id else message_or_callback.from_user.id
    
    now = datetime.utcnow()
    
    # קביעת טווח הזמנים לפי בחירת הנהג
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_name = "היום"
    elif period == "week":
        start_date = now - timedelta(days=now.weekday()) # תחילת השבוע הנוכחי
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        period_name = "השבוע"
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) # תחילת החודש
        period_name = "החודש"
    else:
        start_date = now - timedelta(days=3650) # הכל
        period_name = "כל הזמן"

    # שליפת עבודות שהסתיימו מהטבלה הפעילה
    completed_active = db.query(Job).filter(
        Job.driver_id == user_id,
        Job.status == "completed",
        Job.created_at >= start_date
    ).all()
    
    # שליפת עבודות מהארכיון (כי הבוט שלנו מנקה אוטומטית עבודות ישנות)
    completed_history = db.query(JobHistory).filter(
        JobHistory.driver_id == user_id,
        JobHistory.status == "completed",
        JobHistory.created_at >= start_date
    ).all()
    
    # איחוד כל העבודות
    all_completed = completed_active + completed_history
    
    # חישוב רווחים
    total_earned = 0
    rides_count = 0
    deliveries_count = 0
    
    for job in all_completed:
        try:
            total_earned += float(job.price)
        except ValueError:
            pass # מדלג על מי שהכניס מחיר כמו "50 שקלים" במקום מספר
            
        if job.type == "ride":
            rides_count += 1
        else:
            deliveries_count += 1

    # יצירת המקלדת המחליפה
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="📅 היום" + (" 🟢" if period == "today" else ""), callback_data="dash_filter_today"),
        types.InlineKeyboardButton(text="📆 השבוע" + (" 🟢" if period == "week" else ""), callback_data="dash_filter_week"),
        types.InlineKeyboardButton(text="🗓️ החודש" + (" 🟢" if period == "month" else ""), callback_data="dash_filter_month")
    )
    
    text = (
        f"📊 **דשבורד נהג - סיכום {period_name}:**\n\n"
        f"💰 **הכנסות:** {total_earned:.2f} ₪\n"
        f"✅ **סה\"כ עבודות שהושלמו:** {len(all_completed)}\n"
        f"🚖 **מתוכן נסיעות:** {rides_count}\n"
        f"📦 **מתוכן משלוחים:** {deliveries_count}\n\n"
        f"*(לחץ על הכפתורים למטה כדי לשנות תקופת זמן)*"
    )
    
    if is_edit:
        # אם הנהג לחץ על כפתור - אנחנו רק מעדכנים את הטקסט, לא שולחים הודעה חדשה
        await message_or_callback.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    else:
        # אם הנהג שלח הודעה דרך התפריט - שולחים הודעה חדשה
        await message_or_callback.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
        
    db.close()
