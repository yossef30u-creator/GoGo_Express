from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.models.database import SessionLocal, Job

router = Router()

# ==========================================
# 1. תצוגת העבודות (הפרדה בין נסיעות למשלוחים)
# ==========================================

# --- מסך הנסיעות שלי (לנהגי מוניות) ---
@router.message(F.text == "📅 הנסיעות שלי")
async def show_my_rides(message: types.Message):
    db = SessionLocal()
    # שולף רק עבודות מסוג ride שמשויכות לנהג הזה ובסטטוס פעיל
    jobs = db.query(Job).filter(
        Job.driver_id == message.from_user.id,
        Job.type == "ride",
        Job.status == "assigned"
    ).all()
    
    if not jobs:
        await message.answer("אין לך נסיעות פעילות כרגע. 🚕")
        db.close()
        return

    for job in jobs:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ סיימתי נסיעה", callback_data=f"finish_job_{job.id}")
        kb.button(text="❌ ביטול חירום", callback_data=f"driver_cancel_{job.id}")
        
        await message.answer(
            f"🚖 **נסיעה #{job.id}**\n"
            f"📍 מ: {job.pickup_loc}\n"
            f"🏁 ל: {job.dropoff_loc}\n"
            f"💰 מחיר: {job.price} ₪\n"
            f"📝 הערות: {job.notes if job.notes else 'אין'}",
            reply_markup=kb.as_markup()
        )
    db.close()

# --- מסך המשלוחים שלי (לשליחים) ---
@router.message(F.text == "📦 המשלוחים שלי")
async def show_my_deliveries(message: types.Message):
    db = SessionLocal()
    # שולף רק עבודות מסוג delivery שמשויכות לשליח הזה ובסטטוס פעיל
    jobs = db.query(Job).filter(
        Job.driver_id == message.from_user.id,
        Job.type == "delivery",
        Job.status == "assigned"
    ).all()
    
    if not jobs:
        await message.answer("אין לך משלוחים פעילים כרגע. 📦")
        db.close()
        return

    for job in jobs:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ חבילה נמסרה", callback_data=f"finish_job_{job.id}")
        kb.button(text="❌ ביטול חירום", callback_data=f"driver_cancel_{job.id}")
        
        await message.answer(
            f"📦 **משלוח #{job.id}**\n"
            f"📍 איסוף: {job.pickup_loc}\n"
            f"🏁 מסירה: {job.dropoff_loc}\n"
            f"⚖️ משקל/גודל: {job.weight if job.weight else 'לא צוין'}\n"
            f"💰 מחיר: {job.price} ₪\n"
            f"📝 הערות: {job.notes if job.notes else 'אין'}",
            reply_markup=kb.as_markup()
        )
    db.close()

# ==========================================
# 2. לוגיקת סיום עבודה (הצלחה) + תוספת מערכת דירוג
# ==========================================

@router.callback_query(F.data.startswith("finish_job_"))
async def finish_job_success(callback: types.CallbackQuery):
    job_id = int(callback.data.split("_")[2])
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if job and job.status == "assigned":
        job.status = "completed"
        driver_id = job.driver_id
        client_id = job.client_id
        job_type_str = "הנסיעה" if job.type == "ride" else "המשלוח"
        db.commit()
        
        emoji = "🚖" if job.type == "ride" else "📦"
        await callback.message.edit_text(f"🎉 **עבודה #{job_id} הסתיימה בהצלחה!** כל הכבוד. {emoji}")
        
        # --- תוספת: יצירת מקלדת הדירוג ללקוח ---
        rating_kb = InlineKeyboardBuilder()
        rating_kb.row(
            types.InlineKeyboardButton(text="⭐", callback_data=f"rate_{driver_id}_1_{job_id}"),
            types.InlineKeyboardButton(text="⭐⭐", callback_data=f"rate_{driver_id}_2_{job_id}"),
            types.InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate_{driver_id}_3_{job_id}")
        )
        rating_kb.row(
            types.InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate_{driver_id}_4_{job_id}"),
            types.InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate_{driver_id}_5_{job_id}")
        )
        
        # הודעה ללקוח שהעסקה הושלמה ובקשת דירוג
        try:
            await callback.bot.send_message(
                client_id,
                f"✅ **{job_type_str} #{job_id} הושלמה!**\n\n"
                f"תודה שהשתמשת בשירות שלנו. נשמח לדעת איך היה השירות!\n"
                f"אנא דרג את הנהג/שליח:",
                reply_markup=rating_kb.as_markup()
            )
        except Exception:
            pass
            
    db.close()
    await callback.answer()

# ==========================================
# 3. לוגיקת ביטול חירום (נהג מבריז/נתקע/לא הסתדר בטלפון)
# ==========================================

@router.callback_query(F.data.startswith("driver_cancel_"))
async def ask_driver_cancel(callback: types.CallbackQuery):
    job_id = int(callback.data.split("_")[2])
    
    kb = InlineKeyboardBuilder()
    kb.button(text="⚠️ כן, אני חייב לבטל", callback_data=f"confirm_driver_cancel_{job_id}")
    kb.button(text="🔙 התחרטתי", callback_data="abort_driver_cancel")
    
    await callback.message.edit_text(
        f"⚠️ **ביטול חירום לעבודה #{job_id}**\n"
        f"האם אתה בטוח שברצונך לבטל? העבודה תחזור מיד למערכת ונהגים אחרים יוכלו לקחת אותה.",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "abort_driver_cancel")
async def abort_driver_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("הפעולה בוטלה. המשך עבודה נעימה! 👍")

@router.callback_query(F.data.startswith("confirm_driver_cancel_"))
async def execute_driver_cancel(callback: types.CallbackQuery):
    job_id = int(callback.data.split("_")[3])
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if job and job.status == "assigned":
        client_id = job.client_id
        job_type = job.type
        
        # 1. עדכון בסיס הנתונים - מחזירים למכרז פתוח
        job.status = "open" 
        job.driver_id = None
        db.commit()
        
        await callback.message.edit_text(f"✅ עבודה #{job_id} בוטלה והוחזרה למערכת. הודעה נשלחה לשאר הנהגים.")
        
        # 2. עדכון הלקוח על הביטול
        try:
            await callback.bot.send_message(
                client_id,
                f"⚠️ **עדכון חשוב:** הנהג נאלץ לבטל את ההגעה לעבודה #{job_id}.\n"
                f"אל דאגה, החזרנו את הבקשה שלך למערכת ואנחנו מחפשים לך נהג חלופי ברגע זה! 🔄"
            )
        except Exception:
            pass

        # 3. --- תוספת: שליחה מחדש (Broadcast) לכל הנהגים הרלוונטיים ---
        try:
            if job_type == "ride":
                from bot.handlers.rides import broadcast_ride
                await broadcast_ride(callback.bot, job)
            else:
                from bot.handlers.deliveries import broadcast_delivery
                await broadcast_delivery(callback.bot, job)
        except Exception as e:
            print(f"Broadcast failed after driver cancel: {e}")
            
    db.close()
    await callback.answer()
