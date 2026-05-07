from aiogram import Router, F, types
from bot.models.database import SessionLocal, User

router = Router()

# 1. מנהל מאשר נהג
@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve_driver(callback: types.CallbackQuery):
    driver_id = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == driver_id).first()
    
    if user:
        user.is_verified = True
        db.commit()
        
        # עדכון הנהג שאישרנו אותו
        try:
            await callback.bot.send_message(
                driver_id, 
                "🎊 **מזל טוב! החשבון שלך אושר.**\nלחץ על `🔄 עבור למסך נהג` בתפריט כדי להתחיל לקבל עבודות."
            )
        except Exception:
            pass # למקרה שהמשתמש חסם את הבוט בינתיים
        
    db.close()
    
    await callback.answer("הנהג אושר בהצלחה!")
    # מעדכן את ההודעה אצלך כדי שתדע שכבר טיפלת בזה
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ **סטטוס: אושר על ידך**", 
        reply_markup=None
    )

# 2. מנהל דוחה נהג
@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_driver(callback: types.CallbackQuery):
    driver_id = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == driver_id).first()
    
    if user:
        user.role = "client" # מחזירים אותו להיות לקוח רגיל בלבד
        user.is_verified = False
        db.commit()
        
        # עדכון הנהג שנדחה
        try:
            await callback.bot.send_message(
                driver_id, 
                "❌ לצערנו, בקשתך להירשם כנהג נדחתה לאחר בדיקת מסמכים.\nלפרטים נוספים אנא פנה לשירות הלקוחות."
            )
        except Exception:
            pass
        
    db.close()
    
    await callback.answer("הנהג נדחה.")
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ **סטטוס: נדחה על ידך**", 
        reply_markup=None
    )
