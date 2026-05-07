from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.models.database import SessionLocal, Job, Bid
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

class BidFlow(StatesGroup):
    waiting_for_counter_offer = State()

# פונקציית עזר: שולחת את ההצעה ללקוח
async def notify_client_about_bid(bot, job, bid):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ קבל הצעה", callback_data=f"client_accept_bid_{bid.id}"))
    builder.row(types.InlineKeyboardButton(text="❌ דחה הצעה", callback_data=f"client_reject_bid_{bid.id}"))

    try:
        await bot.send_message(
            chat_id=job.client_id,
            text=f"🔔 **הצעה חדשה לעבודה שלך!**\n\n"
                 f"הנהג/שליח **{bid.driver_name}** מציע לקחת את העבודה.\n"
                 f"💰 מחיר מוצע: **{bid.price} ₪**\n\n"
                 f"האם תרצה לאשר אותו?",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        print(f"Failed to send bid to client: {e}")

# 1. נהג מסכים למחיר המקורי
@router.callback_query(F.data.startswith("accept_job_"))
async def driver_accept_job(callback: types.CallbackQuery):
    job_id = int(callback.data.split("_")[2])
    db = SessionLocal()
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status != "open":
        await callback.answer("העבודה כבר לא רלוונטית או שנסגרה.", show_alert=True)
        db.close()
        return
        
    new_bid = Bid(
        job_id=job.id,
        driver_id=callback.from_user.id,
        driver_name=callback.from_user.first_name,
        price=job.price,
        status="pending"
    )
    db.add(new_bid)
    db.commit()
    db.refresh(new_bid)
    
    await callback.message.edit_text(f"✅ **ההצעה נשלחה בהצלחה!** (על סך {job.price} ₪).\nממתין לאישור הלקוח...")
    
    # הלקוח יקבל התראה
    await notify_client_about_bid(callback.bot, job, new_bid)
    db.close()

# 2. נהג לוחץ על "הצעה נגדית"
@router.callback_query(F.data.startswith("counter_job_"))
async def driver_counter_job(callback: types.CallbackQuery, state: FSMContext):
    job_id = int(callback.data.split("_")[2])
    await state.update_data(current_job_id=job_id)
    
    await callback.message.answer("💰 **הקלד את הסכום שתרצה להציע (בשקלים בלבד):**")
    await state.set_state(BidFlow.waiting_for_counter_offer)

# 3. נהג מקליד את המחיר החדש
@router.message(BidFlow.waiting_for_counter_offer)
async def process_counter_offer(message: types.Message, state: FSMContext):
    new_price = message.text
    data = await state.get_data()
    job_id = data['current_job_id']
    
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if job and job.status == "open":
        new_bid = Bid(
            job_id=job_id,
            driver_id=message.from_user.id,
            driver_name=message.from_user.first_name,
            price=new_price,
            status="pending"
        )
        db.add(new_bid)
        db.commit()
        db.refresh(new_bid)
        
        await message.answer(f"✅ **ההצעה הנגדית שלך ({new_price} ₪) נשלחה ללקוח!** ממתין לאישור.")
        
        # הלקוח יקבל התראה
        await notify_client_about_bid(message.bot, job, new_bid)
    else:
        await message.answer("אופס, העבודה כבר לא זמינה.")
        
    db.close()
    await state.clear()
    
# 4. נהג מתעלם
@router.callback_query(F.data.startswith("ignore_job_"))
async def ignore_job(callback: types.CallbackQuery):
    await callback.message.delete()

# ==========================================
# פעולות של הלקוח (אישור/דחיית הצעת נהג)
# ==========================================

# 5. הלקוח מאשר את ההצעה
@router.callback_query(F.data.startswith("client_accept_bid_"))
async def client_accept_bid(callback: types.CallbackQuery):
    bid_id = int(callback.data.split("_")[3])
    db = SessionLocal()
    
    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    if not bid:
        await callback.answer("ההצעה לא נמצאה.", show_alert=True)
        db.close()
        return
        
    job = db.query(Job).filter(Job.id == bid.job_id).first()
    if not job or job.status != "open":
        await callback.answer("העבודה כבר נסגרה או לא זמינה.", show_alert=True)
        db.close()
        return

    # עדכון סטטוסים במסד הנתונים
    job.status = "assigned" # העבודה סגורה ומשויכת
    bid.status = "accepted"
    db.commit()
    
    # עדכון הודעת הלקוח
    await callback.message.edit_text(
        f"✅ **אישרת את ההצעה!**\nהעבודה נמסרה לנהג: **{bid.driver_name}**\nבמחיר: {bid.price} ₪."
    )
    
    # שליחת הודעת ניצחון לנהג עם פרטי העבודה
    try:
        await callback.bot.send_message(
            chat_id=bid.driver_id,
            text=f"🎉 **מזל טוב! הלקוח אישר את ההצעה שלך!**\n\n"
                 f"📍 **איסוף:** {job.pickup_loc}\n"
                 f"🏁 **מסירה:** {job.dropoff_loc}\n"
                 f"⚖️ **פירוט:** {job.weight}\n"
                 f"💰 **תשלום שיש לגבות:** {bid.price} ₪\n"
                 f"📝 **הערות לקוח:** {job.notes}\n\n"
                 f"סע בזהירות!"
        )
    except Exception:
        pass
        
    db.close()

# 6. הלקוח דוחה את ההצעה
@router.callback_query(F.data.startswith("client_reject_bid_"))
async def client_reject_bid(callback: types.CallbackQuery):
    bid_id = int(callback.data.split("_")[3])
    db = SessionLocal()
    
    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    if bid:
        bid.status = "rejected"
        db.commit()
        
        # עדכון הלקוח
        await callback.message.edit_text(f"❌ דחית את ההצעה של {bid.driver_name} על סך {bid.price} ₪.")
        
        # עדכון הנהג שנדחה
        try:
            await callback.bot.send_message(
                chat_id=bid.driver_id,
                text=f"❌ הלקוח דחה את ההצעה שלך על סך {bid.price} ₪ עבור עבודת המשלוח."
            )
        except Exception:
            pass
            
    db.close()
