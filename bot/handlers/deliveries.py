from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.models.database import SessionLocal, Job
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.models.database import User

# === תוספת: ייבוא מילון המחוזות ממסך הנהג ===
from bot.handlers.driver_actions import REGIONS_MAP

# === תוספת: מנוע התאמת המיקום החכם ===
def is_driver_relevant(driver_work_regions: str, job_region: str, pickup_address: str) -> bool:
    if not driver_work_regions:
        return False
        
    # מפצל את הערים שנבחרו לפי פסיק
    chosen_regions = [r.strip() for r in driver_work_regions.split(",")]
    
    for driver_region in chosen_regions:
        if driver_region.startswith("CITY:"):
            city = driver_region.replace("CITY:", "")
            if city in pickup_address:
                return True
                
        elif driver_region.startswith("ALL:"):
            region = driver_region.replace("ALL:", "")
            if region == job_region:
                return True
            # בודק גם בתוך כתובת הלקוח למקרה של חוסר התאמה במחוז
            region_cities = REGIONS_MAP.get(region, [])
            for city in region_cities:
                if city in pickup_address:
                    return True
                    
        else: # תאימות למשתמשים ישנים ב-DB
            if driver_region == job_region:
                return True
                
    return False
# ============================================

router = Router()

class DeliveryFlow(StatesGroup):
    waiting_for_region = State() # השלב החדש שנוסף לבחירת אזור
    waiting_for_pickup = State()
    waiting_for_dropoff = State()
    waiting_for_weight = State()
    waiting_for_pickup_date = State()   
    waiting_for_pickup_time = State()   
    waiting_for_dropoff_date = State()  
    waiting_for_dropoff_time = State()  
    waiting_for_price = State()
    waiting_for_notes = State()
    waiting_for_confirmation = State()

@router.message(F.text == "📦 שליחת חבילה")
async def start_delivery(message: types.Message, state: FSMContext):
    
    # === תוספת: חסימת ספאם (הגבלת מקסימום 3 הזמנות פעילות ללקוח) ===
    db = SessionLocal()
    active_jobs_count = db.query(Job).filter(
        Job.client_id == message.from_user.id,
        Job.status.in_(["open", "assigned", "pending_decision"])
    ).count()
    db.close()

    if active_jobs_count >= 3:
        await message.answer(
            "❌ **הגעת למכסת ההזמנות הפעילות.**\n"
            "לא ניתן לפתוח יותר מ-3 הזמנות במקביל. תוכל לסיים או לבטל הזמנות קיימות תחת '📋 ההזמנות שלי'."
        )
        return
    # ==============================================================

    # הוספת מקלדת בחירת אזור
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="מרכז"), types.KeyboardButton(text="דרום")],
        [types.KeyboardButton(text="צפון"), types.KeyboardButton(text="ירושלים")]
    ], resize_keyboard=True)
    
    await message.answer("📍 **באיזה אזור המשלוח מתבצע?**\n(בחר מהכפתורים)", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(DeliveryFlow.waiting_for_region)

# ה-Handler החדש ששומר את האזור וממשיך לאיסוף
@router.message(DeliveryFlow.waiting_for_region)
async def region_delivery(message: types.Message, state: FSMContext):
    await state.update_data(region=message.text)
    
    # --- תוספת: כפתור בקשת מיקום GPS ---
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📍 שלח מיקום נוכחי", request_location=True)],
        [types.KeyboardButton(text="🏠 הקלד כתובת ידנית")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(
        "📦 **מאיפה אוספים את החבילה?**\n\n"
        "באפשרותך ללחוץ על הכפתור למטה כדי לשלוח מיקום מדויק (GPS), או להקליד כתובת ידנית.\n"
        "*(לדוגמה: בני ברק, רחוב רמבם 10)*", 
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_pickup)

@router.message(DeliveryFlow.waiting_for_pickup)
async def pickup_delivery(message: types.Message, state: FSMContext):
    # --- תוספת: טיפול בקבלת מיקום GPS לעומת טקסט ---
    if message.location:
        lat = message.location.latitude
        lng = message.location.longitude
        await state.update_data(pickup="מיקום GPS (צמוד למפה)", pickup_lat=lat, pickup_lng=lng)
        await message.answer("📍 המיקום נקלט בהצלחה!", reply_markup=types.ReplyKeyboardRemove())
    else:
        # המשתמש הקליד טקסט (או לחץ על הכפתור "הקלד כתובת ידנית")
        pickup_text = message.text
        if pickup_text == "🏠 הקלד כתובת ידנית":
            await message.answer("אנא הקלד את הכתובת המלאה כעת:", reply_markup=types.ReplyKeyboardRemove())
            return # נחכה להודעה הבאה שלו שהיא הטקסט עצמו
            
        await state.update_data(pickup=pickup_text, pickup_lat=None, pickup_lng=None)
        await message.answer("📍 הכתובת נקלטה בהצלחה!", reply_markup=types.ReplyKeyboardRemove())
    # ---------------------------------------------

    await message.answer(
        "🏁 **לאן למסור את החבילה?**\n\n"
        "⚠️ *הוראה:* חובה להזין **כתובת מלאה** ליעד.\n"
        "*(לדוגמה: תל אביב, רחוב קיבוץ גלויות 12)*",
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_dropoff)

@router.message(DeliveryFlow.waiting_for_dropoff)
async def dropoff_delivery(message: types.Message, state: FSMContext):
    await state.update_data(dropoff=message.text)
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="✉️ מעטפה / מסמכים"), types.KeyboardButton(text="🛍️ קטן (עד 5 ק\"ג)")],
        [types.KeyboardButton(text="📦 בינוני (5-15 ק\"ג)"), types.KeyboardButton(text="🏋️ כבד (מעל 15 ק\"ג)")]
    ], resize_keyboard=True)
    
    await message.answer("⚖️ **מה גודל / משקל החבילה?**\n(בחר מהכפתורים או הקלד)", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(DeliveryFlow.waiting_for_weight)

@router.message(DeliveryFlow.waiting_for_weight)
async def weight_delivery(message: types.Message, state: FSMContext):
    await state.update_data(weight=message.text)
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📅 היום"), types.KeyboardButton(text="📅 מחר")]
    ], resize_keyboard=True)
    
    await message.answer(
        "📅 **באיזה יום תרצה שיאספו את החבילה?**\n\n"
        "*(בחר 'היום' או 'מחר', או פשוט הקלד תאריך אחר, לדוגמה: 20/05)*",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_pickup_date)

@router.message(DeliveryFlow.waiting_for_pickup_date)
async def pickup_date_delivery(message: types.Message, state: FSMContext):
    await state.update_data(pickup_date=message.text)
    
    await message.answer(
        "⏰ **ממתי עד מתי אפשר לאסוף את החבילה מהכתובת שלך?**\n\n"
        "⚠️ *הוראה:* נא להזין **שעות איסוף מדויקות**.\n"
        "*(לדוגמה: 06:00 עד 12:00, או 14:00-18:00)*", 
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_pickup_time)

@router.message(DeliveryFlow.waiting_for_pickup_time)
async def pickup_time_delivery(message: types.Message, state: FSMContext):
    await state.update_data(pickup_time=message.text)
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📅 היום"), types.KeyboardButton(text="📅 מחר")]
    ], resize_keyboard=True)
    
    await message.answer(
        "📅 **באיזה יום תרצה שימסרו את החבילה ביעד?**\n\n"
        "*(בחר 'היום' או 'מחר', או פשוט הקלד תאריך אחר, לדוגמה: 21/05)*",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_dropoff_date)

@router.message(DeliveryFlow.waiting_for_dropoff_date)
async def dropoff_date_delivery(message: types.Message, state: FSMContext):
    await state.update_data(dropoff_date=message.text)
    
    await message.answer(
        "⏳ **ממתי עד מתי אפשר למסור את החבילה ביעד?**\n\n"
        "⚠️ *הוראה:* נא להזין **שעות מסירה מדויקות**.\n"
        "*(לדוגמה: 17:00 עד 23:00, או 08:00-12:00)*", 
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_dropoff_time)

@router.message(DeliveryFlow.waiting_for_dropoff_time)
async def dropoff_time_delivery(message: types.Message, state: FSMContext):
    await state.update_data(dropoff_time=message.text)
    
    await message.answer(
        "💰 **כמה תהיה מוכן לשלם על המשלוח?**\n\n"
        "*(כתוב סכום בשקלים, למשל: 50, או 'הצעה של שליח')*",
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_price)

@router.message(DeliveryFlow.waiting_for_price)
async def price_delivery(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="⏩ דלג")]
    ], resize_keyboard=True)
    
    await message.answer(
        "📝 **הודעה חופשית/הערות לשליח?**\n\n"
        "⚠️ *הוראה:* כאן ניתן לכתוב פרטים נוספים (למשל: קומה 2 בלי מעלית, להשאיר ליד הדלת, שביר).\n"
        "*(אם אין הערות, לחץ על 'דלג')*", 
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(DeliveryFlow.waiting_for_notes)

@router.message(DeliveryFlow.waiting_for_notes)
async def notes_delivery(message: types.Message, state: FSMContext):
    notes_text = message.text if message.text != "⏩ דלג" else "אין הערות"
    await state.update_data(notes=notes_text)
    
    data = await state.get_data()
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🚀 פרסם משלוח", callback_data="pub_delivery")],
        [types.InlineKeyboardButton(text="❌ ביטול", callback_data="cancel")]
    ])
    
    full_pickup = f"{data['pickup_date']} | שעות: {data['pickup_time']}"
    full_dropoff = f"{data['dropoff_date']} | שעות: {data['dropoff_time']}"
    
    await state.update_data(full_pickup_time=full_pickup)
    await state.update_data(full_dropoff_time=full_dropoff)

    # נוסף האזור לסיכום
    summary = (
        f"📋 **סיכום משלוח:**\n\n"
        f"📍 **אזור:** {data['region']}\n"
        f"📍 **מאיפה:** {data['pickup']}\n"
        f"🏁 **לאן:** {data['dropoff']}\n"
        f"⚖️ **משקל:** {data['weight']}\n"
        f"📤 **איסוף:** {full_pickup}\n"
        f"📥 **מסירה:** {full_dropoff}\n"
        f"💰 **תשלום:** {data['price']} ₪\n"
        f"📝 **הערות:** {notes_text}\n\n"
        f"הכל נכון? לפרסם לשליחים באזור?"
    )
    await message.answer(summary, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(DeliveryFlow.waiting_for_confirmation)

@router.callback_query(F.data == "pub_delivery", DeliveryFlow.waiting_for_confirmation)
async def pub_delivery(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db = SessionLocal()
    
    # נוסף האזור (region) וקואורדינטות ה-GPS לשמירה ב-DB
    new_job = Job(
        type="delivery", 
        status="open", 
        region=data['region'],
        pickup_loc=data['pickup'], 
        pickup_lat=data.get('pickup_lat'), # שומר קואורדינטות ב-DB אם יש
        pickup_lng=data.get('pickup_lng'), # שומר קואורדינטות ב-DB אם יש
        dropoff_loc=data['dropoff'],
        weight=data['weight'],
        pickup_time=data['full_pickup_time'], 
        deadline=data['full_dropoff_time'],
        price=data['price'],
        notes=data.get('notes', ""),
        client_id=callback.from_user.id
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # הפעלת פונקציית ההפצה המופרדת
    await broadcast_delivery(callback.bot, new_job)

    await callback.message.edit_text(
        f"✅ **משלוח #{new_job.id} פורסם בהצלחה!**\nהועבר לשליחים באזור {new_job.region}. תקבל התראה כשנהג יגיש הצעה.", 
        parse_mode="Markdown"
    )
    db.close()
    
    # מחזיר לתפריט הראשי של הלקוח
    from bot.main import get_keyboard
    user = SessionLocal().query(User).filter(User.telegram_id == callback.from_user.id).first()
    markup = get_keyboard(user)
    await callback.message.answer("הזמנתך נמצאת בטיפול.", reply_markup=markup)
    
    await state.clear()


# =====================================================================
# פונקציה ציבורית (Public Function) להפצת המשלוח לשליחים
# (הופרד לפונקציה כדי שקבצים אחרים כמו scheduler וביטולים יוכלו לקרוא לו)
# =====================================================================
async def broadcast_delivery(bot_instance, job_obj: Job):
    db = SessionLocal()
    active_drivers = db.query(User).filter(
        User.role == "driver",
        User.driver_type.in_(["delivery", "both"]), # מוודא שרק שליחים או "גם וגם" יקבלו
        User.is_available == True,
        User.is_verified == True
    ).all()

    for driver in active_drivers:
        # כאן מופעל המנוע החכם שבנינו כדי לוודא ששליח מקבל רק עבודות באזור שלו
        if is_driver_relevant(driver.work_regions, job_obj.region, job_obj.pickup_loc):
            
            # --- תוספת: יצירת מקלדת חכמה עם Waze אם יש GPS ---
            builder = InlineKeyboardBuilder()
            if job_obj.pickup_lat and job_obj.pickup_lng:
                waze_url = f"https://waze.com/ul?ll={job_obj.pickup_lat},{job_obj.pickup_lng}&navigate=yes"
                builder.row(types.InlineKeyboardButton(text="📍 נווט ב-Waze לאיסוף", url=waze_url))
                
            builder.row(types.InlineKeyboardButton(text=f"✅ מקבל ב-{job_obj.price} ₪", callback_data=f"accept_job_{job_obj.id}"))
            builder.row(types.InlineKeyboardButton(text="💰 הצעה נגדית", callback_data=f"counter_job_{job_obj.id}"))
            builder.row(types.InlineKeyboardButton(text="❌ התעלם", callback_data=f"ignore_job_{job_obj.id}"))
            
            try:
                await bot_instance.send_message(
                    driver.telegram_id,
                    f"🔔 **עבודת משלוח חדשה!** 🔔\n\n"
                    f"🌍 אזור: {job_obj.region}\n"
                    f"📍 מ: {job_obj.pickup_loc}\n"
                    f"🏁 ל: {job_obj.dropoff_loc}\n"
                    f"📦 משקל/גודל: {job_obj.weight}\n"
                    f"💰 מחיר מוצע: {job_obj.price} ₪\n"
                    f"📝 הערות: {job_obj.notes}",
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )
                
                # תוספת בונוס: שליחת ה-GPS במפה קטנה לשליח אם נשלח על ידי הלקוח
                if job_obj.pickup_lat and job_obj.pickup_lng:
                    await bot_instance.send_location(
                        chat_id=driver.telegram_id,
                        latitude=job_obj.pickup_lat,
                        longitude=job_obj.pickup_lng
                    )
            except Exception:
                pass 
    db.close()
