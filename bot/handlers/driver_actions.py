from aiogram import Router, F, types
from bot.models.database import SessionLocal, User

router = Router()

# 1. שינוי סטטוס זמינות נהג 
@router.message(F.text.in_(["🔴 התנתק (כרגע מחובר)", "🟢 התחבר (כרגע מנותק)"]))
async def toggle_driver_availability(message: types.Message):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if user and user.role == "driver":
        # אם הוא לחץ על "התחבר", סימן שהוא רוצה להיות זמין
        if "התחבר" in message.text:
            user.is_available = True
            status_str = "מחובר 🟢"
        else:
            user.is_available = False
            status_str = "מנותק 🔴"
            
        db.commit()
        
        # ייבוא המקלדת בתוך הפונקציה כדי למנוע התנגשות קבצים (Circular Import)
        from bot.main import get_keyboard 
        markup = get_keyboard(user)
        
        await message.answer(f"הסטטוס שלך עודכן. אתה עכשיו: **{status_str}**", reply_markup=markup)
    
    db.close()

# 2. שינוי אזור עבודה
@router.message(F.text == "📍 שנה אזור עבודה")
async def change_region_prompt(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="מרכז", callback_data="set_region_מרכז"),
         types.InlineKeyboardButton(text="דרום", callback_data="set_region_דרום")],
        [types.InlineKeyboardButton(text="צפון", callback_data="set_region_צפון"),
         types.InlineKeyboardButton(text="ירושלים", callback_data="set_region_ירושלים")]
    ])
    await message.answer("בחר את אזור העבודה החדש שלך:", reply_markup=kb)

@router.callback_query(F.data.startswith("set_region_"))
async def set_new_region(callback: types.CallbackQuery):
    new_region = callback.data.split("_")[2]
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    if user:
        user.work_regions = new_region
        db.commit()
        
    db.close()
    
    # עוצר את סמל הטעינה על הכפתור
    await callback.answer() 
    await callback.message.edit_text(f"✅ אזור העבודה שלך עודכן בהצלחה ל: **{new_region}**")
