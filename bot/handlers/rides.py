from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.models.database import SessionLocal, Job

router = Router()

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
    await message.answer(
        "🚖 **מאיפה לאסוף אותך?**\n\n"
        "⚠️ *הוראה:* חובה להזין **כתובת מלאה** כדי שהנהג ימצא אותך בקלות.\n"
        "*(לדוגמה: בני ברק, רחוב רמבם 10)*", 
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(RideFlow.waiting_for_pickup)

@router.message(RideFlow.waiting_for_pickup)
async def pickup_ride(message: types.Message, state: FSMContext):
    await state.update_data(pickup=message.text)
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
    
    new_job = Job(
        type="ride", 
        status="open", 
        pickup_loc=data['pickup'], 
        dropoff_loc=data['dropoff'],
        weight=data['weight'], # זה בעצם שומר את מספר הנוסעים
        pickup_time=data['full_pickup_time'], 
        deadline=None, # ריק, כי אין חלון מסירה בנסיעה
        price=data['price'],
        notes=data.get('notes', "")
    )
    db.add(new_job)
    db.commit()
    await callback.message.edit_text(
        f"✅ **נסיעה #{new_job.id} פורסמה בהצלחה!**\nהיא מועברת כעת לנהגים זמינים.", 
        parse_mode="Markdown"
    )
    db.close()
    await state.clear()
