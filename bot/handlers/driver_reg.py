from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.models.database import SessionLocal, User
from datetime import datetime

# הגדר את ה-ID שלך כמנהל כאן כדי שתקבל את ההתראות!
ADMIN_ID = 552041081  # החלף ל-ID האמיתי שלך

router = Router()

# הגדרת השלבים של טופס ההרשמה
class DriverRegFlow(StatesGroup):
    waiting_for_type = State()
    waiting_for_phone = State()
    waiting_for_name = State()
    waiting_for_license_photo = State()
    waiting_for_license_expiry = State()
    waiting_for_regions = State()

# 1. תחילת ההרשמה
@router.message(F.text == "🆔 הרשמה כנהג/שליח")
async def start_driver_registration(message: types.Message, state: FSMContext):
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
    
    await message.answer("קיבלנו את המספר! ✅\nאנא הקלד את **שמך המלא** (שם פרטי ושם משפחה):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(DriverRegFlow.waiting_for_name)

# 4. קבלת שם ובקשת צילום רישיון
@router.message(DriverRegFlow.waiting_for_name, F.text)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    
    await message.answer("תודה. כעת, אנא **צלם והעלה תמונה של רישיון הנהיגה שלך**.\n(התמונה נשמרת בצורה מאובטחת לצורך אימות בלבד).")
    await state.set_state(DriverRegFlow.waiting_for_license_photo)

# 5. קבלת תמונה ובקשת תאריך תפוגה
@router.message(DriverRegFlow.waiting_for_license_photo, F.photo)
async def process_license_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(license_file_id=file_id)
    
    await message.answer("התמונה התקבלה! 📸\nמהו **תאריך התפוגה** של רישיון הנהיגה שלך?\nאנא הקלד בפורמט: **DD/MM/YYYY** (לדוגמה: 31/12/2026)")
    await state.set_state(DriverRegFlow.waiting_for_license_expiry)

# 6. קבלת תאריך תפוגה ואימות (Validation)
@router.message(DriverRegFlow.waiting_for_license_expiry, F.text)
async def process_license_expiry(message: types.Message, state: FSMContext):
    try:
        expiry_date = datetime.strptime(message.text, "%d/%m/%Y").date()
    except ValueError:
        await message.answer("❌ הפורמט לא תקין.\nאנא הקלד את התאריך בדיוק כך: **DD/MM/YYYY** (לדוגמה: 01/05/2027)")
        return
        
    await state.update_data(license_expiry=expiry_date)
    
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="מרכז"), types.KeyboardButton(text="דרום")],
        [types.KeyboardButton(text="צפון"), types.KeyboardButton(text="ירושלים")]
    ], resize_keyboard=True)
    
    await message.answer("מצוין. שאלה אחרונה: **באיזה אזור** אתה מעדיף לעבוד בעיקר?", reply_markup=kb)
    await state.set_state(DriverRegFlow.waiting_for_regions)

# 7. סיום הרישום, שמירה ל-DB והמתנה לאישור
@router.message(DriverRegFlow.waiting_for_regions, F.text)
async def finish_registration(message: types.Message, state: FSMContext):
    data = await state.get_data()
    region = message.text
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user:
        user.role = "driver"
        user.driver_type = data['driver_type']
        user.phone = data['phone']
        user.full_name = data['full_name']
        user.driver_license_file_id = data['license_file_id']
        user.license_expiry = data['license_expiry']
        user.work_regions = region
        user.is_verified = False # חשוב: ממתין לאישור מנהל!
        user.is_active = True
        
        db.commit()
    db.close()
    
    await message.answer(
        "🎉 **הפרטים שלך נקלטו במערכת בהצלחה!**\n\n"
        "החשבון שלך כרגע מוגדר כ-**'ממתין לאישור'**.\n"
        "המנהלים שלנו יבדקו את המסמכים שהעלית.\n"
        "ברגע שהחשבון יאושר, תקבל הודעה ותוכל להתחיל לקבל עבודות! 💸",
        reply_markup=types.ReplyKeyboardRemove()
    )

    # יצירת מקלדת אישור למנהל (הכפתורים יטופלו בקובץ הניהול)
    admin_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ אשר נהג", callback_data=f"admin_approve_{message.from_user.id}"),
            types.InlineKeyboardButton(text="❌ דחה", callback_data=f"admin_reject_{message.from_user.id}")
        ]
    ])

    # שליחת התראה ללוח המנהל (ל-ID שלך)
    try:
        await message.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=data['license_file_id'],
            caption=(
                f"👤 **בקשת רישום נהג חדשה!**\n\n"
                f"שם: {data['full_name']}\n"
                f"טלפון: {data['phone']}\n"
                f"סוג: {data['driver_type']}\n"
                f"אזור: {region}\n"
                f"תוקף רישיון: {data['license_expiry'].strftime('%d/%m/%Y')}\n"
            ),
            reply_markup=admin_kb
        )
    except Exception as e:
        print(f"Failed to send admin notification: {e}")
    
    # החזרת תפריט הלקוח בינתיים
    from bot.main import get_keyboard
    kb = get_keyboard(user)
    await message.answer("בינתיים, חזרת לתפריט הראשי:", reply_markup=kb)
    
    await state.clear()
