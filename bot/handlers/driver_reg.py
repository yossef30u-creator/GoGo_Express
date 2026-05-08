from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder # תוספת לבניית מקלדות פנימיות
from bot.models.database import SessionLocal, User, Job 
from datetime import datetime

# ייבוא רק של מילון האזורים כדי לשמור על מקור אמת אחד (ללא ייבוא המקלדות של נהג פעיל)
from bot.handlers.driver_actions import REGIONS_MAP

# הגדר את ה-ID שלך כמנהל כאן כדי שתקבל את ההתראות!
ADMIN_ID = 552041081  # החלף ל-ID האמיתי שלך

router = Router()

# ==========================================
# מקלדות ייעודיות לתהליך ההרשמה (למניעת התנגשויות)
# ==========================================
def get_reg_regions_markup():
    builder = InlineKeyboardBuilder()
    for region in REGIONS_MAP.keys():
        builder.button(text=region, callback_data=f"reg_view_region_{region}")
    builder.adjust(2)
    return builder.as_markup()

def get_reg_cities_markup(region_name, selected_list=[]):
    builder = InlineKeyboardBuilder()
    cities = REGIONS_MAP.get(region_name, [])
    
    all_tag = f"ALL:{region_name}"
    all_text = f"✅ 📍 כל מחוז {region_name}" if all_tag in selected_list else f"📍 כל מחוז {region_name}"
    builder.button(text=all_text, callback_data=f"reg_toggle_loc_{all_tag}")
    
    for city in cities:
        city_tag = f"CITY:{city}"
        text = f"✅ {city}" if city_tag in selected_list else city
        builder.button(text=text, callback_data=f"reg_toggle_loc_{city_tag}")
    
    builder.button(text="🚀 שמור בחירה 🚀", callback_data="reg_finish_saving")
    builder.button(text="🗺️ חזרה למחוזות", callback_data="reg_back_to_regions_menu")
    
    builder.adjust(1)
    return builder.as_markup()
# ==========================================

# הגדרת השלבים של טופס ההרשמה
class DriverRegFlow(StatesGroup):
    waiting_for_type = State()
    waiting_for_phone = State()
    waiting_for_name = State()
    waiting_for_license_photo = State()
    waiting_for_license_expiry = State()
    waiting_for_regions = State()

# 1. תחילת ההרשמה עם בדיקות חסימה חכמות
@router.message(F.text == "🆔 הרשמה כנהג/שליח")
async def start_driver_registration(message: types.Message, state: FSMContext):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user and user.role == "driver":
        # מקרה א': כבר מאושר
        if user.is_verified:
            if user.driver_type == 'both':
                await message.answer("הנך כבר רשום ומאושר כנהג ומשלוחן במערכת! ✅")
            else:
                current = "נהג מונית" if user.driver_type == "taxi" else "שליח"
                other = "משלוחים" if user.driver_type == "taxi" else "מוניות"
                await message.answer(f"אתה כבר רשום כ-{current}. 🚖\nבמידה ותרצה להוסיף הרשאה גם ל{other}, אנא פנה למנהל לעדכון הפרופיל שלך.")
            db.close()
            return
        
        # מקרה ב': נרשם וממתין לאישור
        if not user.is_verified:
            type_str = "נהג מונית" if user.driver_type == 'taxi' else "שליח" if user.driver_type == 'delivery' else "נהג ומשלוחן"
            await message.answer(
                f"⏳ **ההרשמה שלך כ-{type_str} בבדיקה.**\n\n"
                f"אין צורך להירשם שוב. ברגע שהמנהל יאשר את המסמכים שלך, תקבל הודעה ותוכל להתחיל לעבוד!"
            )
            db.close()
            return

    # בדיקה אם חסום
    if user and not user.is_active:
        await message.answer("⚠️ חשבונך הושעה במערכת. אנא פנה למנהל לבירור.")
        db.close()
        return

    db.close()
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="🚖 נהג מונית")],
        [types.KeyboardButton(text="📦 שליח (רכב/קטנוע)")],
        [types.KeyboardButton(text="🔄 גם וגם")]
    ], resize_keyboard=True)
    
    await message.answer("ברוך הבא לנבחרת שלנו! 🚀\nכדי להתחיל, בחר את סוג הפעילות שלך:", reply_markup=kb)
    await state.set_state(DriverRegFlow.waiting_for_type)

# 2. קבלת סוג נהג ובקשת טלפון
@router.message(DriverRegFlow.waiting_for_type, F.text.in_(["🚖 נהג מונית", "📦 שליח (רכב/קטנוע)", "🔄 גם וגם"]))
async def process_driver_type(message: types.Message, state: FSMContext):
    type_map = {"🚖 נהג מונית": "taxi", "📦 שליח (רכב/קטנוע)": "delivery", "🔄 גם וגם": "both"}
    await state.update_data(driver_type=type_map[message.text])
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📱 שלח מספר טלפון", request_contact=True)]
    ], resize_keyboard=True)
    
    await message.answer("מעולה. כעת, לחץ על הכפתור למטה כדי לשתף את מספר הטלפון שלך:", reply_markup=kb)
    await state.set_state(DriverRegFlow.waiting_for_phone)

# 3. קבלת טלפון ובקשת שם מלא
@router.message(DriverRegFlow.waiting_for_phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await message.answer("קיבלנו את המספר! ✅\nאנא הקלד את **שמך המלא** (פרטי ומשפחה):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(DriverRegFlow.waiting_for_name)

# 4. שם ובקשת צילום
@router.message(DriverRegFlow.waiting_for_name, F.text)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("תודה. כעת, אנא **צלם והעלה תמונה של רישיון הנהיגה שלך**.")
    await state.set_state(DriverRegFlow.waiting_for_license_photo)

# 5. תמונה ובקשת תאריך
@router.message(DriverRegFlow.waiting_for_license_photo, F.photo)
async def process_license_photo(message: types.Message, state: FSMContext):
    await state.update_data(license_file_id=message.photo[-1].file_id)
    await message.answer("התמונה התקבלה! 📸\nמהו **תאריך התפוגה** של הרישיון?\nבפורמט: **DD/MM/YYYY** (לדוגמה: 31/12/2026)")
    await state.set_state(DriverRegFlow.waiting_for_license_expiry)

# 6. תאריך ואימות
@router.message(DriverRegFlow.waiting_for_license_expiry, F.text)
async def process_license_expiry(message: types.Message, state: FSMContext):
    try:
        expiry_date = datetime.strptime(message.text, "%d/%m/%Y").date()
        if expiry_date <= datetime.now().date():
            await message.answer("❌ לא ניתן להירשם עם רישיון שפג תוקפו. הקלד תאריך עתידי:")
            return
    except ValueError:
        await message.answer("❌ הפורמט לא תקין. הקלד כך: DD/MM/YYYY")
        return
        
    await state.update_data(license_expiry=expiry_date)
    await message.answer("מצוין. באיזה מחוז תרצה לעבוד?", reply_markup=get_reg_regions_markup())
    await state.set_state(DriverRegFlow.waiting_for_regions)

# 6.5 ניווט אזורים
@router.callback_query(DriverRegFlow.waiting_for_regions, F.data.startswith("reg_view_region_"))
async def reg_show_cities_in_region(callback: types.CallbackQuery, state: FSMContext):
    region_name = callback.data.replace("reg_view_region_", "")
    await state.update_data(current_region=region_name, selected_locs=[])
    await callback.message.edit_text(f"בחר ערים ב{region_name}:", reply_markup=get_reg_cities_markup(region_name, []))

@router.callback_query(DriverRegFlow.waiting_for_regions, F.data.startswith("reg_toggle_loc_"))
async def reg_toggle_location(callback: types.CallbackQuery, state: FSMContext):
    loc_tag = callback.data.replace("reg_toggle_loc_", "")
    data = await state.get_data()
    selected = data.get("selected_locs", [])
    if loc_tag in selected:
        selected.remove(loc_tag)
    else:
        selected.append(loc_tag)
    await state.update_data(selected_locs=selected)
    await callback.message.edit_reply_markup(reply_markup=get_reg_cities_markup(data.get("current_region"), selected))
    await callback.answer()

@router.callback_query(DriverRegFlow.waiting_for_regions, F.data == "reg_back_to_regions_menu")
async def reg_back_to_regions(callback: types.CallbackQuery):
    await callback.message.edit_text("בחר מחוז עבודה:", reply_markup=get_reg_regions_markup())
    await callback.answer()

# 7. סיום הרישום ושמירה
@router.callback_query(DriverRegFlow.waiting_for_regions, F.data == "reg_finish_saving")
async def finish_registration(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    selected = data.get("selected_locs", [])
    
    if not selected:
        await callback.answer("⚠️ חובה לבחור לפחות עיר אחת!", show_alert=True)
        return
        
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    if user:
        user.role = "driver"
        user.current_mode = "client" # נשאר במצב לקוח עד אישור
        user.driver_type = data['driver_type']
        user.phone = data['phone']
        user.full_name = data['full_name']
        user.driver_license_file_id = data['license_file_id']
        user.license_expiry = data['license_expiry'] 
        user.work_regions = ",".join(selected)
        user.is_verified = False
        user.is_active = True
        db.commit()
    
    # כפתור חזרה לדף הבית בסיום הרשמה
    home_kb = InlineKeyboardBuilder()
    home_kb.button(text="🏠 חזרה לדף הבית", callback_data="back_to_home")

    # --- תוספת: הודעת סיום מותאמת אישית ---
    type_str_reg = "כנהג מונית" if data['driver_type'] == 'taxi' else "כשליח" if data['driver_type'] == 'delivery' else "כנהג ושליח"
    
    await callback.message.edit_text(
        f"🎉 **הפרטים שלך נקלטו במערכת בהצלחה!**\n\n"
        f"החשבון שלך {type_str_reg} מוגדר כ-'ממתין לאישור'.\n"
        f"ברגע שהמנהל יאשר את המסמכים, תקבל הודעה ותוכל להתחיל לעבוד.\n"
        f"בינתיים, חזרת לתפריט הלקוח.",
        reply_markup=home_kb.as_markup()
    )

    # התראה למנהל
    admin_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ אשר נהג", callback_data=f"admin_approve_{callback.from_user.id}"),
         types.InlineKeyboardButton(text="❌ דחה", callback_data=f"admin_reject_{callback.from_user.id}")]
    ])

    await callback.message.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=data['license_file_id'],
        caption=f"👤 **בקשת רישום נהג!**\nשם: {data['full_name']}\nסוג: {data['driver_type']}\nאזורים: {len(selected)} ערים",
        reply_markup=admin_kb
    )
    
    db.close()
    await state.clear()

# ==========================================
# Handlers לכפתורי הבית והכניסה למסך העבודה
# ==========================================

@router.callback_query(F.data == "back_to_home")
async def back_to_home_handler(callback: types.CallbackQuery):
    from bot.main import get_keyboard
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    kb = get_keyboard(user)
    await callback.message.answer("ברוך הבא חזרה לתפריט הראשי!", reply_markup=kb)
    await callback.message.delete()
    db.close()
    await callback.answer()

# כפתור שהנהג מקבל בהודעת ה"מזל טוב" מהמנהל
@router.callback_query(F.data == "enter_driver_mode")
async def enter_driver_mode(callback: types.CallbackQuery):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    if user and user.is_verified:
        user.current_mode = "driver"
        db.commit()
        from bot.main import get_keyboard
        
        # --- תוספת: הודעת כניסה מותאמת אישית ---
        mode_text = "נהג מונית 🚖" if user.driver_type == "taxi" else "שליח 📦" if user.driver_type == "delivery" else "נהג מונית ושליח 🚖📦"
        
        await callback.message.answer(
            f"🎊 **שלום {user.full_name}!**\n"
            f"נכנסת למצב עבודה כ{mode_text}.\n"
            "כאן יופיעו הזמנות רלוונטיות עבורך לפי אזורי העבודה שהגדרת.",
            reply_markup=get_keyboard(user)
        )
        await callback.message.delete()
    else:
        await callback.answer("החשבון שלך עדיין אינו מאושר.", show_alert=True)
    
    db.close()
    await callback.answer()
