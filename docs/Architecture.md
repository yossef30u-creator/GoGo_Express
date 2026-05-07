​Architecture.md — ארכיטקטורה ומבנה המערכת
​1. מבנה שכבות (Layered Architecture)
​כדי למנוע "קוד ספגטי" שקורס בשינוי קטן, המערכת מחולקת ל-4 שכבות:
​Telegram Handlers: השכבה החיצונית ביותר. רק מקבלת פקודות מהמשתמש ומעבירה הלאה.
​Service Layer (The Brain): כאן נמצאת הלוגיקה – חישוב ETA, התאמת נהג לנסיעה, ניהול תורים.
​Data Access Layer (Models): עבודה מול בסיס הנתונים (SQLAlchemy).
​Worker Layer: מערכת חיצונית שרצה ברקע ובודקת זמנים ותקינות.
​2. מודל הנתונים (Database Schema - High Level)
​Users Table: id, telegram_id, role (driver/client), phone, rating, is_verified, current_state.
​Jobs Table: id, type (ride/delivery), status (open/active/completed/expired), pickup_loc, dropoff_loc, pickup_time (timestamp), created_at, driver_id, client_id, eta_minutes.
​Audit Logs: טבלה שרושמת כל שינוי סטטוס קריטי לצורך שחזור (Rollback) במקרה של תקלה.
​3. מערכות פיקוח ובקרה (System Oversight)
​The Watchdog: סקריפט נפרד שבודק כל 60 שניות אם הבוט הראשי "חי" (Pulse check). אם לא – הוא מאתחל אותו ושולח התראה למנהל.
​Rate Limiter: שכבת הגנה ב-Redis שחוסמת משתמשים שמציפים בבקשות, כדי למנוע קריסת ה-API.
​Transaction Integrity: כל אישור נסיעה מתבצע תחת Database Lock – כדי ששני נהגים בחיים לא יוכלו לאשר את אותה נסיעה בו-זמנית.
​4. ניהול משימות מתוזמנות (The Time Engine)
​Future Jobs Queue: משימות עתידיות נשמרות ב-DB ומנוטרות על ידי APScheduler.
​Logic: 15 דקות לפני מועד איסוף עתידי, המערכת מוודאת שהנהג פעיל. אם לא – המשימה נפתחת מחדש לכלל הנהגים כ"דחופה".
​Execution Plan (Next Steps)
​כדי להתקדם לביצוע (BUILD) של הקוד עצמו, אנחנו צריכים להגדיר את הקבצים הראשוניים.

# הצעה למבנה תיקיות ראשוני להעתקה
mkdir -p bot/{handlers,services,models,utils} scripts/monitoring
touch bot/main.py bot/config.py bot/models/database.py README.md

Risks
​API Latency: אם טלגרם יאטו את התגובה, הבוט ירגיש "תקוע". פתרון: שימוש ב-Asyncio לכל פעולות ה-I/O.
​Data Consistency: במקרה של נפילת שרת באמצע כתיבה ל-DB. פתרון: שימוש ב-Database Transactions.