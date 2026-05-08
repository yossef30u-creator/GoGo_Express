from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.models.database import SessionLocal, Job, User  # הוספנו את User כדי למשוך נהגים
from aiogram.utils.keyboard import InlineKeyboardBuilder # תוספת לבניית מקלדת דינמית לנהג
from bot.handlers.driver_actions import REGIONS_MAP
from geopy.geocoders import Nominatim
import time
from geopy.distance import geodesic

# === תוספת: מנוע התאמת המיקום החכם ===
def is_driver_relevant(driver_work_region: str, pickup_address: str) -> bool:
    if not driver_work_region:
        return False
        
    # המשתמש מזין כתובת מלאה, אז נבדוק אם שם העיר נמצא בתוך הכתובת
    if driver_work_region.startswith("CITY:"):
        driver_city = driver_work_region.replace("CITY:", "")
        return driver_city in pickup_address
        
    if driver_work_region.startswith("ALL:"):
        driver_region = driver_work_region.replace("ALL:", "")
        region_cities = REGIONS_MAP.get(driver_region, [])
        
        # בודק אם אחת מערי המחוז מופיעה בכתובת שהלקוח הקליד
        for city in region_cities:
            if city in pickup_address:
                return True
                
        if driver_region in pickup_address:
            return True
            
    # Fallback למקרה של הגדרות ישנות
    # תמיכה במצב של בחירה מרובה (Multiple Regions) המופרדים בפסיקים
    for region in driver_work_region.split(","):
        if is_driver_relevant_single(region, pickup_address):
            return True
    return False

def is_driver_relevant_single(single_region: str, pickup_address: str) -> bool:
    if single_region.startswith("CITY:"):
        return single_region.replace("CITY:", "") in pickup_address
    if single_region.startswith("ALL:"):
        region_name = single_region.replace("ALL:", "")
        region_cities = REGIONS_MAP.get(region_name, [])
        for city in region_cities:
            if city in pickup_address:
                return True
        if region_name in pickup_address:
            return True
    return single_region in pickup_address
# ============================================

# יצירת אובייקט המפות (מחוץ לפונקציה כדי לחסוך זמן טעינה)
geolocator = Nominatim(user_agent="GoGo_Express_Bot")

def extract_region_from_address(address: str) -> str:
    """הופך כתובת טקסטואלית לאזור גיאוגרפי מוגדר"""
    
    # 1. בדיקה מהירה: האם המשתמש כתב מילה שאנחנו כבר מכירים?
    for region_name, cities in REGIONS_MAP.items():
        if region_name in address:
            return region_name
        for city in cities:
            if city in address:
                return city

    # 2. חיפוש חכם במפה (אם לא מצאנו ברשימה הידנית)
    try:
        # מוסיפים ", ישראל" כדי שהחיפוש יהיה ממוקד
        query = f"{address}, ישראל"
        location = geolocator.geocode(query, addressdetails=True, timeout=10)

        if location and 'address' in location.raw:
            addr = location.raw['address']
            
            # שליפת המחוז מהמפה (state / city / town)
            # המפה מחזירה שמות כמו "South District" או "מחוז הדרום"
            state_info = addr.get('state', '') + addr.get('city', '') + addr.get('town', '')
            
            # מיפוי השמות של המפה לאזורים של הבוט שלנו
            if any(word in state_info for word in ["South", "דרום", "באר שבע", "נגב"]):
                return "דרום"
            if any(word in state_info for word in ["North", "צפון", "חיפה", "גליל"]):
                return "צפון"
            if any(word in state_info for word in ["Center", "מרכז", "תל אביב", "Tel Aviv"]):
                return "מרכז"
            if any(word in state_info for word in ["Jerusalem", "ירושלים"]):
                return "ירושלים"
            
            # אם מדובר בעיר ספציפית שהמפה מצאה
            return addr.get('city') or addr.get('town') or addr.get('village') or "כללי"

    except Exception as e:
        print(f"⚠️ שגיאת מפה: {e}")
    
    return "כללי"

#================================

class RideFlow(StatesGroup):
    waiting_for_pickup = State()
    waiting_for_dropoff = State()
    waiting_for_passengers = State() # החלפנו משקל בנוסעים
    waiting_for_pickup_date = State()   
    waiting_for_pickup_time = State()   
    # הסרנו את שלבי ההגעה ליעד!
    waiting_for_price = State()
    waiting_for_notes = State() # הודעה חופשית
    waiting_for_confirmation = State()

@router.message(F.text == "🚖 הזמנת נסיעה")
async def start_ride(message: types.Message, state: FSMContext):
    
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

    # --- תוספת: כפתור בקשת מיקום GPS ---
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📍 שלח מיקום נוכחי", request_location=True)],
        [types.KeyboardButton(text="🏠 הקלד כתובת ידנית")]
    ], resize_keyboard=True, one_time_keyboard=True)

    await message.answer(
        "🚖 **מאיפה לאסוף אותך?**\n\n"
        "באפשרותך ללחוץ על הכפתור למטה כדי לשלוח מיקום מדויק (GPS), או להקליד כתובת ידנית.\n"
        "*(לדוגמה: בני ברק, רחוב רמבם 10)*", 
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_pickup)

@router.message(RideFlow.waiting_for_pickup)
async def pickup_ride(message: types.Message, state: FSMContext):
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
        "🏁 **לאן נוסעים?**\n\n"
        "⚠️ *הוראה:* חובה להזין **כתובת מלאה** ליעד.\n"
        "*(לדוגמה: תל אביב, רחוב קיבוץ גלויות 12)*",
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_dropoff)

@router.message(RideFlow.waiting_for_dropoff)
async def dropoff_ride(message: types.Message, state: FSMContext):
    await state.update_data(dropoff=message.text)
    
    # כפתורים מותאמים למספר נוסעים
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="👤 1"), types.KeyboardButton(text="👥 2")],
        [types.KeyboardButton(text="👨‍👩‍👧 3"), types.KeyboardButton(text="👨‍👩‍👧‍👦 4 ומעלה")]
    ], resize_keyboard=True)
    
    await message.answer("👥 **כמה נוסעים אתם?**\n(בחר מהכפתורים או הקלד)", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(RideFlow.waiting_for_passengers)

@router.message(RideFlow.waiting_for_passengers)
async def passengers_ride(message: types.Message, state: FSMContext):
    # שומרים את הנוסעים בתוך 'weight' כדי שזה ייכנס יפה לאותה עמודה במסד הנתונים הקיים
    await state.update_data(weight=message.text)
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📅 היום"), types.KeyboardButton(text="📅 מחר")]
    ], resize_keyboard=True)
    
    await message.answer(
        "📅 **באיזה יום תרצו שיאספו אתכם?**\n\n"
        "*(בחר 'היום' או 'מחר', או פשוט הקלד תאריך אחר, לדוגמה: 20/05)*",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_pickup_date)

@router.message(RideFlow.waiting_for_pickup_date)
async def pickup_date_ride(message: types.Message, state: FSMContext):
    await state.update_data(pickup_date=message.text)
    
    await message.answer(
        "⏰ **ממתי עד מתי אפשר לאסוף אתכם?**\n\n"
        "⚠️ *הוראה:* נא להזין **שעות איסוף מדויקות**.\n"
        "*(לדוגמה: 06:00 עד 12:00, או 14:00-18:00)*", 
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_pickup_time)

@router.message(RideFlow.waiting_for_pickup_time)
async def pickup_time_ride(message: types.Message, state: FSMContext):
    await state.update_data(pickup_time=message.text)
    
    # כאן אנחנו מדלגים ישירות למחיר (בלי שאלות על הגעה ליעד)
    await message.answer(
        "💰 **כמה תהיו מוכנים לשלם על הנסיעה?**\n\n"
        "*(כתוב סכום בשקלים, למשל: 50, או 'הצעה של נהג')*",
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_price)

@router.message(RideFlow.waiting_for_price)
async def price_ride(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    
    # שלב ההערות החופשיות
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="⏩ דלג")]
    ], resize_keyboard=True)
    
    await message.answer(
        "📝 **הודעה חופשית/הערות לנהג?**\n\n"
        "⚠️ *הוראה:* כאן ניתן לכתוב פרטים נוספים (למשל: צריך כסא תינוק, יש הרבה מזוודות).\n"
        "*(אם אין הערות, לחץ על 'דלג')*", 
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_notes)

@router.message(RideFlow.waiting_for_notes)
async def notes_ride(message: types.Message, state: FSMContext):
    notes_text = message.text if message.text != "⏩ דלג" else "אין הערות"
    await state.update_data(notes=notes_text)
    
    data = await state.get_data()
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🚀 פרסם נסיעה", callback_data="pub_ride")],
        [types.InlineKeyboardButton(text="❌ ביטול", callback_data="cancel")]
    ])
    
    # עיבוד הנתונים לסיכום סופי
    full_pickup = f"{data['pickup_date']} | שעות: {data['pickup_time']}"
    await state.update_data(full_pickup_time=full_pickup)

    summary = (
        f"📋 **סיכום נסיעה:**\n\n"
        f"📍 **מאיפה:** {data['pickup']}\n"
        f"🏁 **לאן:** {data['dropoff']}\n"
        f"👥 **נוסעים:** {data['weight']}\n"
        f"📤 **איסוף:** {full_pickup}\n"
        f"💰 **תשלום:** {data['price']} ₪\n"
        f"📝 **הערות:** {notes_text}\n\n"
        f"הכל נכון? לפרסם לנהגים באזור?"
    )
    await message.answer(summary, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(RideFlow.waiting_for_confirmation)

@router.callback_query(F.data == "pub_ride", RideFlow.waiting_for_confirmation)
async def pub_ride(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db = SessionLocal()
    
    # --- תיקון: חילוץ GPS גם מכתובת טקסטואלית ---
    p_lat = data.get('pickup_lat')
    p_lng = data.get('pickup_lng')
    
    if not p_lat: # אם המשתמש הקליד ידנית ולא שלח GPS
        try:
            loc = geolocator.geocode(f"{data['pickup']}, ישראל", timeout=10)
            if loc:
                p_lat, p_lng = loc.latitude, loc.longitude
        except:
            pass
    # --------------------------------------------

    detected_region = extract_region_from_address(data['pickup'])

    new_job = Job(
        client_id=callback.from_user.id,
        type="ride", 
        status="open", 
        pickup_loc=data['pickup'], 
        pickup_lat=p_lat, # עכשיו יש לנו מספרים!
        pickup_lng=p_lng, # עכשיו יש לנו מספרים!
        dropoff_loc=data['dropoff'],
        weight=data['weight'],
        pickup_time=data['full_pickup_time'], 
        price=data['price'],
        notes=data.get('notes', ""),
        region=detected_region
    )
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job) # כדי לקבל את ה-ID החדש שנוצר
    
    await callback.message.edit_text(
        f"✅ **נסיעה #{new_job.id} פורסמה בהצלחה!**\nהיא מועברת כעת לנהגים זמינים.", 
        parse_mode="Markdown"
    )
    
    # הפעלת פונקציית ההפצה
    await broadcast_ride(callback.bot, new_job)

    db.close()
    
    # מחזיר לתפריט הראשי
    from bot.main import get_keyboard
    user = SessionLocal().query(User).filter(User.telegram_id == callback.from_user.id).first()
    markup = get_keyboard(user)
    await callback.message.answer("הזמנתך נמצאת בטיפול.", reply_markup=markup)
    
    await state.clear()


# =====================================================================
# פונקציה ציבורית (Public Function) להפצת הנסיעה לנהגים
# (הופרד לפונקציה כדי שקבצים אחרים כמו scheduler וביטולים יוכלו לקרוא לו)
# =====================================================================
async def broadcast_ride(bot_instance, job_obj: Job):
    db = SessionLocal()
    active_drivers = db.query(User).filter(
        User.role == "driver",
        User.driver_type.in_(["taxi", "both"]), 
        User.is_available == True,
        User.is_verified == True
    ).all()
    
    driver_msg = (
        f"📢 **נסיעה חדשה באזורך!**\n\n"
        f"📍 **מאיפה:** {job_obj.pickup_loc}\n"
        f"🏁 **לאן:** {job_obj.dropoff_loc}\n"
        f"👥 **נוסעים:** {job_obj.weight}\n"
        f"⏰ **איסוף:** {job_obj.pickup_time}\n"
        f"💰 **תשלום:** {job_obj.price} ₪\n"
        f"📝 **הערות:** {job_obj.notes}\n"
    )
    
    # --- תוספת: יצירת מקלדת חכמה עם Waze אם יש GPS ---
    builder = InlineKeyboardBuilder()
    if job_obj.pickup_lat and job_obj.pickup_lng:
        waze_url = f"https://waze.com/ul?ll={job_obj.pickup_lat},{job_obj.pickup_lng}&navigate=yes"
        builder.row(types.InlineKeyboardButton(text="📍 נווט ב-Waze לאיסוף", url=waze_url))
        
    builder.row(types.InlineKeyboardButton(text="✅ אני לוקח", callback_data=f"take_job_{job_obj.id}"))
    driver_kb = builder.as_markup()
    # ------------------------------------------------

    for driver in active_drivers:
    should_notify = False

    # תנאי 1: האם זה באזור העבודה הקבוע שלו?
    if is_driver_relevant(driver.work_regions, job_obj.pickup_loc):
        should_notify = True

    # תנאי 2: בדיקת GPS (רק אם הנהג הפעיל רדיוס ויש נתוני מיקום)
    # נניח ששמרנו לנהג שדה שנקרא pref_radius (למשל 10 ק"מ)
    if not should_notify and driver.last_lat and driver.last_lng and job_obj.pickup_lat:
        distance = geodesic(
            (job_obj.pickup_lat, job_obj.pickup_lng),
            (driver.last_lat, driver.last_lng)
        ).km
        
        # אם הנהג הגדיר רדיוס (למשל 20 ק"מ) והוא בטווח
        if driver.pref_radius and distance <= driver.pref_radius:
            should_notify = True

    # אם אחד התנאים עבד - שולחים!
    if should_notify:
        try:
            await bot_instance.send_message(
                chat_id=driver.telegram_id,
                text=f"🔔 {driver_msg}", # נוסיף פעמון שיידע שזה התראה
                reply_markup=driver_kb,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error: {e}")