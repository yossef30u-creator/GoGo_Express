from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext  
from bot.models.database import SessionLocal, User

router = Router()

# מילון האזורים המרכזי - מקור האמת היחיד של הבוט
REGIONS_MAP = {
    "ירושלים והסביבה": [
        "ירושלים", "מודיעין-מכבים-רעות", "בית שמש", "מעלה אדומים", 
        "מבשרת ציון", "גבעת זאב", "צור הדסה"
    ],
    "תל אביב וגוש דן": [
        "תל אביב-יפו", "רמת גן", "גבעתיים", "בני ברק", "חולון", "בת ים", 
        "אור יהודה", "קריית אונו", "יהוד-מונוסון", "גבעת שמואל"
    ],
    "המרכז והשפלה": [
        "ראשון לציון", "פתח תקווה", "רחובות", "נס ציונה", "לוד", "רמלה", 
        "באר יעקב", "שוהם", "יבנה", "מזכרת בתיה", "גדרה", "אלעד"
    ],
    "השרון": [
        "נתניה", "הרצליה", "רעננה", "כפר סבא", "הוד השרון", "רמת השרון", 
        "טייבה", "טירה", "כפר יונה", "תל מונד", "אבן יהודה"
    ],
    "צפון וחיפה": [
        "חיפה", "קריות", "עכו", "נהריה", "כרמיאל", "טבריה", "נצרת", 
        "נוף הגליל", "עפולה", "בית שאן", "צפת", "קצרין", "יוקנעם עילית"
    ],
    "דרום": [
        "באר שבע", "אשדוד", "אשקלון", "אילת", "נתיבות", "שדרות", 
        "אופקים", "דימונה", "ערד", "קריית גת", "קריית מלאכי"
    ],
    "יהודה ושומרון": [
        "מודיעין עילית", "ביתר עילית", "אריאל", "אפרת", "אורנית", 
        "אלפי מנשה", "קרני שומרון", "קדומים", "קריית ארבע"
    ]
}

# פונקציות עזר לייצור מקלדות
def get_regions_markup():
    builder = InlineKeyboardBuilder()
    for region in REGIONS_MAP.keys():
        builder.button(text=region, callback_data=f"view_region_{region}")
    builder.adjust(2)
    return builder.as_markup()

# עדכון מקלדת: תומכת בסימון ✅ ורשימת נבחרים
def get_cities_markup(region_name, selected_list=[]):
    builder = InlineKeyboardBuilder()
    cities = REGIONS_MAP.get(region_name, [])
    
    # בדיקה האם "כל המחוז" נבחר
    all_tag = f"ALL:{region_name}"
    all_text = f"✅ 📍 כל מחוז {region_name}" if all_tag in selected_list else f"📍 כל מחוז {region_name}"
    builder.button(text=all_text, callback_data=f"toggle_loc_ALL:{region_name}")
    
    for city in cities:
        city_tag = f"CITY:{city}"
        # אם העיר ברשימה, נוסיף ✅ לשם הכפתור
        text = f"✅ {city}" if city_tag in selected_list else city
        builder.button(text=text, callback_data=f"toggle_loc_{city_tag}")
    
    # --- שדרוג האייקונים כאן ---
    builder.button(text="🚀 שמור בחירה 🚀", callback_data="finish_saving_regions")
    builder.button(text="🗺️ חזרה למחוזות", callback_data="back_to_regions_menu")
    
    builder.adjust(1)
    return builder.as_markup()

# --- Handlers ---

# 1. שינוי סטטוס זמינות נהג (נשאר ללא שינוי)
@router.message(F.text.in_(["🔴 התנתק (כרגע מחובר)", "🟢 התחבר (כרגע מנותק)"]))
async def toggle_driver_availability(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user and user.role == "driver":
        if "התחבר" in message.text:
            user.is_available = True
            status_str = "מחובר 🟢"
        else:
            user.is_available = False
            status_str = "מנותק 🔴"
            
        db.commit()
        
        from bot.main import get_keyboard 
        markup = get_keyboard(user)
        
        await message.answer(f"הסטטוס שלך עודכן. אתה עכשיו: **{status_str}**", reply_markup=markup)
    
    db.close()

# 2. שינוי אזור עבודה - פתיחת התפריט
@router.message(F.text == "📍 שנה אזור עבודה")
async def change_region_prompt(message: types.Message):
    await message.answer("בחר את מחוז העבודה שלך:", reply_markup=get_regions_markup())

# כניסה למחוז ספציפי - מאפס את הבחירות ב-State
@router.callback_query(F.data.startswith("view_region_"))
async def show_cities_in_region(callback: types.CallbackQuery, state: FSMContext):
    region_name = callback.data.split("_")[2]
    await state.update_data(current_region=region_name, selected_locs=[])
    await callback.message.edit_text(
        f"בחר את הערים ב{region_name} (ניתן לבחור כמה) ולסיום לחץ שמור:",
        reply_markup=get_cities_markup(region_name, [])
    )

# לוגיקה שמדליקה ומכבה את ה-✅
@router.callback_query(F.data.startswith("toggle_loc_"))
async def toggle_location(callback: types.CallbackQuery, state: FSMContext):
    loc_tag = callback.data.replace("toggle_loc_", "")
    data = await state.get_data()
    selected = data.get("selected_locs", [])
    region_name = data.get("current_region")
    
    if loc_tag in selected:
        selected.remove(loc_tag)
    else:
        selected.append(loc_tag)
        
    await state.update_data(selected_locs=selected)
    
    # עדכון המקלדת ללא שליחת הודעה חדשה
    await callback.message.edit_reply_markup(
        reply_markup=get_cities_markup(region_name, selected)
    )
    await callback.answer()

# שמירה סופית של כל האזורים שנבחרו (רק לעדכון אזורים, לא בזמן הרשמה!)
@router.callback_query(F.data == "finish_saving_regions")
async def save_multiple_regions(callback: types.CallbackQuery, state: FSMContext):
    # בדיקה האם המשתמש באמצע הרשמה (כדי למנוע התנגשות עם driver_reg.py)
    current_state = await state.get_state()
    if current_state and "waiting_for_regions" in current_state:
        # מתעלם, כי driver_reg.py יטפל בזה!
        return

    data = await state.get_data()
    selected = data.get("selected_locs", [])
    
    if not selected:
        await callback.answer("⚠️ חובה לבחור לפחות עיר אחת או את כל המחוז!", show_alert=True)
        return
        
    # שחרור מיידי של כפתור הטעינה בטלגרם כדי שלא ייתקע
    await callback.answer()
    
    # הפיכה למחרוזת אחת עם פסיקים לשמירה ב-DB
    final_regions_string = ",".join(selected)
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    markup = None # נכין משתנה למקלדת
    
    if user:
        user.work_regions = final_regions_string
        db.commit()
        # --- בניית המקלדת הראשית של הנהג ---
        try:
            from bot.main import get_keyboard
            markup = get_keyboard(user)
        except ImportError:
            pass # למקרה נדיר של שגיאת ייבוא, הבוט לא יקרוס
    db.close()
    
    # הצגת שמות הערים שנבחרו למשתמש (ללא הקידומות)
    display_names = [s.split(":")[1] for s in selected]
    cities_str = ", ".join(display_names)
    
    await callback.message.edit_text(f"✅ אזורי העבודה שלך עודכנו בהצלחה ל: **{cities_str}**", parse_mode="Markdown")
    
    # --- שליחת ההודעה שמושכת את התפריט חזרה למטה ---
    if markup:
        await callback.message.answer("חזרת לתפריט הראשי. סע בזהירות! 🚗", reply_markup=markup)
    
    # איפוס הזיכרון כדי לא להתקע ב-State
    await state.clear()

@router.callback_query(F.data == "back_to_regions_menu")
async def back_to_regions(callback: types.CallbackQuery):
    await callback.message.edit_text("בחר את מחוז העבודה שלך:", reply_markup=get_regions_markup())
    await callback.answer()
