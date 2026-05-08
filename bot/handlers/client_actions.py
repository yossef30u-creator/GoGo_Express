from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
# הוספנו את User לייבוא כדי שנוכל לעדכן את הדירוג שלו
from bot.models.database import SessionLocal, Job, User 

router = Router()

# הגדרת מצב המתנה להקלדת מחיר חדש
class UpdatePriceFlow(StatesGroup):
    waiting_for_new_price = State()

# 1. הצגת כל ההזמנות הפתוחות של הלקוח
@router.message(F.text == "📋 ההזמנות שלי")
async def show_my_orders(message: types.Message):
    db = SessionLocal()
    
    # תוספת קריטית: הוספנו את "pending_decision" כדי שהזמנות שממתינות להעלאת מחיר לא ייעלמו מהמסך!
    active_jobs = db.query(Job).filter(
        Job.client_id == message.from_user.id,
        Job.status.in_(["open", "assigned", "pending_decision"])
    ).all()
    
    # --- תוספת: כפתור גישה להיסטוריית ההזמנות ---
    history_kb = InlineKeyboardBuilder()
    history_kb.button(text="📜 היסטוריית הזמנות", callback_data="client_job_history")
    
    if not active_jobs:
        await message.answer(
            "אין לך הזמנות פעילות כרגע. תוכל להזמין נסיעה או משלוח דרך התפריט הראשי! 🚕📦", 
            reply_markup=history_kb.as_markup()
        )
        db.close()
        return

    await message.answer("הנה ההזמנות הפעילות שלך:", reply_markup=history_kb.as_markup())

    for job in active_jobs:
        # התאמת הטקסט גם לסטטוס ההמתנה להחלטה
        status_hebrew = "✅ שודך נהג" if job.status == "assigned" else "🔍 מחפש נהג..."
        job_type = "🚖 נסיעה" if job.type == "ride" else "📦 משלוח"
        
        kb = InlineKeyboardBuilder()
        # מפנה לפונקציית בדיקת הביטול
        kb.button(text="❌ ביטול הזמנה", callback_data=f"ask_cancel_{job.id}")
        
        await message.answer(
            f"**{job_type} #{job.id}**\n"
            f"📍 מ: {job.pickup_loc}\n"
            f"🏁 ל: {job.dropoff_loc}\n"
            f"💰 מחיר: {job.price} ₪\n"
            f"📊 סטטוס: **{status_hebrew}**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
    db.close()

# 2. כשהלקוח לוחץ על ביטול - בדיקת סטטוס לפני מחיקה
@router.callback_query(F.data.startswith("ask_cancel_"))
async def prompt_cancel_job(callback: types.CallbackQuery):
    job_id = int(callback.data.split("_")[2])
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        await callback.answer("ההזמנה לא נמצאה.", show_alert=True)
        db.close()
        return

    if job.status == "assigned":
        # אם יש נהג בדרך, נוודא איתו שוב
        kb = InlineKeyboardBuilder()
        kb.button(text="⚠️ כן, בטל בכל זאת", callback_data=f"confirm_cancel_{job.id}")
        kb.button(text="🔙 התחרטתי, השאר הזמנה", callback_data="abort_cancel")
        
        await callback.message.edit_text(
            f"⚠️ **שים לב!** להזמנה #{job.id} כבר שודך נהג.\nהאם אתה בטוח שברצונך לבטל אותה עכשיו?",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
    else:
        # אם אין נהג (open או pending_decision), מבטלים מיד
        job.status = "cancelled"
        db.commit()
        await callback.message.edit_text(f"🗑️ הזמנה #{job.id} בוטלה בהצלחה.")
    
    db.close()

# 3. הלקוח החליט לא לבטל ברגע האחרון
@router.callback_query(F.data == "abort_cancel")
async def abort_cancellation(callback: types.CallbackQuery):
    await callback.message.edit_text("הפעולה בוטלה. ההזמנה שלך נשארת פעילה! 👍")

# 4. הלקוח מאשר ביטול למרות שיש נהג בדרך
@router.callback_query(F.data.startswith("confirm_cancel_"))
async def execute_cancel_assigned_job(callback: types.CallbackQuery):
    job_id = int(callback.data.split("_")[2])
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if job and job.status == "assigned":
        old_driver_id = job.driver_id
        job.status = "cancelled"
        db.commit()
        
        await callback.message.edit_text(f"🗑️ הזמנה #{job_id} בוטלה. נעדכן את הנהג.")
        
        # התראה לנהג שהלקוח ביטל לו את העבודה בפרצוף
        if old_driver_id:
            try:
                await callback.bot.send_message(
                    chat_id=old_driver_id,
                    text=f"⚠️ **עדכון דחוף:** הלקוח ביטל הרגע את נסיעה/משלוח #{job_id}.\n"
                         f"אין צורך להגיע לכתובת. אנו מתנצלים על חוסר הנוחות.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
                
    db.close()

# ==========================================
# תוספת: טיפול בהעלאת/עדכון מחיר (מהסקדיולר)
# ==========================================

# א. כשהלקוח לוחץ על הכפתור "עדכון מחיר"
@router.callback_query(F.data.startswith("raise_price_"))
async def ask_for_new_price(callback: types.CallbackQuery, state: FSMContext):
    job_id = int(callback.data.split("_")[2])
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if job and job.status == "pending_decision":
        # שומרים את ה-ID של הנסיעה בזיכרון
        await state.update_data(job_id=job_id)
        
        # מחשבים דוגמה כדי לעזור ללקוח
        try:
            suggested_price = int(job.price) + 10
            example_text = f"לדוגמה: הקלד {suggested_price} כדי להוסיף 10 ₪."
        except ValueError:
            example_text = "הקלד את הסכום החדש במספרים בלבד."
            
        await callback.message.edit_text(
            f"המחיר הקודם שהצעת היה **{job.price} ₪**.\n"
            f"כמה תרצה להציע עכשיו כדי למשוך נהגים?\n"
            f"({example_text})"
        )
        # מכניסים את הלקוח למצב המתנה להקלדה
        await state.set_state(UpdatePriceFlow.waiting_for_new_price)
        
    db.close()
    await callback.answer()

# ב. כשהלקוח מקליד את המחיר החדש
@router.message(UpdatePriceFlow.waiting_for_new_price, F.text)
async def process_new_price(message: types.Message, state: FSMContext):
    new_price = message.text.strip()
    
    # בדיקה שבאמת הוקלד מספר
    if not new_price.isdigit():
        await message.answer("❌ אנא הקלד סכום במספרים בלבד (לדוגמה: 50).")
        return

    data = await state.get_data()
    job_id = data.get("job_id")

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if job and job.status == "pending_decision":
        job.price = new_price
        job.status = "open"  # מחזירים לסטטוס חיפוש
        db.commit()
        
        await message.answer(f"✅ המחיר עודכן ל-**{new_price} ₪**! מחפש נהגים מחדש... 🚀")
        
        # משדרים מחדש את הנסיעה לכל הנהגים הרלוונטיים
        try:
            if job.type == "ride":
                from bot.handlers.rides import broadcast_ride
                await broadcast_ride(message.bot, job)
            else:
                from bot.handlers.deliveries import broadcast_delivery
                await broadcast_delivery(message.bot, job)
        except Exception as e:
            print(f"Error rebroadcasting: {e}")
            
    db.close()
    await state.clear() # יוצאים ממצב ההמתנה

# ==========================================
# לוגיקת קליטת הדירוג מהלקוח
# ==========================================
@router.callback_query(F.data.startswith("rate_"))
async def process_driver_rating(callback: types.CallbackQuery):
    # הפורמט: rate_driverId_stars_jobId
    parts = callback.data.split("_")
    driver_id = int(parts[1])
    stars = int(parts[2])
    job_id = int(parts[3])
    
    db = SessionLocal()
    # חיפוש הנהג לפי טלגרם ID
    driver = db.query(User).filter(User.telegram_id == driver_id).first()
    
    if driver:
        # בדיקה שהערכים קיימים (למקרה של משתמש ישן)
        if driver.rating_sum is None:
            driver.rating_sum = 0.0
        if driver.rating_count is None:
            driver.rating_count = 0
            
        # עדכון הנתונים
        driver.rating_sum += stars
        driver.rating_count += 1
        db.commit()
        
        # חישוב הממוצע החדש
        avg_rating = driver.rating_sum / driver.rating_count
        
        await callback.message.edit_text(
            f"⭐ **דירגת את השירות ב-{stars} כוכבים!**\n"
            f"תודה רבה על המשוב. הדירוג הממוצע של הנהג הוא כעת {avg_rating:.1f} ⭐.",
            parse_mode="Markdown"
        )
        
        # שליחת הודעת עידוד לנהג אם קיבל 5 כוכבים
        if stars == 5:
            try:
                await callback.bot.send_message(
                    driver_id,
                    f"🌟 **כל הכבוד!**\nהלקוח מעבודה #{job_id} דירג אותך ב-5 כוכבים! המשך כך."
                )
            except Exception:
                pass
    else:
        await callback.message.edit_text("❌ חלה שגיאה: לא הצלחתי לעדכן את הדירוג במערכת.")
        
    db.close()
    await callback.answer()

# ==========================================
# תוספת: דף היסטוריית עבודות ללקוח
# ==========================================
@router.callback_query(F.data == "client_job_history")
async def show_client_history(callback: types.CallbackQuery):
    db = SessionLocal()
    
    # שולף את 10 העבודות האחרונות של הלקוח בסטטוס שהסתיים/בוטל (מסודר מהחדש לישן)
    history_jobs = db.query(Job).filter(
        Job.client_id == callback.from_user.id,
        Job.status.in_(["completed", "cancelled"])
    ).order_by(Job.id.desc()).limit(10).all()
    
    if not history_jobs:
        await callback.message.edit_text("עדיין אין לך היסטוריית הזמנות במערכת. 📜")
        db.close()
        return
        
    text = "📜 **10 ההזמנות האחרונות שלך:**\n\n"
    for job in history_jobs:
        job_type = "🚖 נסיעה" if job.type == "ride" else "📦 משלוח"
        status_icon = "✅ הושלם" if job.status == "completed" else "❌ בוטל"
        
        text += f"**{job_type} #{job.id}**\n"
        text += f"📍 מ: {job.pickup_loc}\n"
        text += f"🏁 ל: {job.dropoff_loc}\n"
        text += f"💰 מחיר: {job.price} ₪\n"
        text += f"סטטוס: {status_icon}\n"
        text += "〰️〰️〰️〰️〰️〰️\n"
        
    # כפתור חזרה לתפריט
    kb = InlineKeyboardBuilder()
    kb.button(text="סגור היסטוריה", callback_data="close_history")
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.as_markup())
    db.close()
    await callback.answer()

@router.callback_query(F.data == "close_history")
async def close_history(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()
