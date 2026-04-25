# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
import datetime
import json

# ==================== SETTINGS ====================
BOT_TOKEN = "8538355821:AAE6u-r4BlTKrGzOQVSvE1rzgJQNbvUBIcU"
ADMIN_ID = 217420509
VIP_GROUP_ID = -1003803654378
DB_FILE = "vip_bot.db"
SETTINGS_FILE = "bot_settings.json"

DEFAULT_SETTINGS = {
    "welcome_message": "ברוך הבא לבוט הסדרות הטורקיות!\n\nכאן תוכל לצפות בכל הסדרות הטורקיות האהובות!\n\nהתוכן זמין אך ורק למנויים VIP",
    "support_username": "your_username",
    "bit_link": "",
    "paybox_link": "",
    "paypal_email": "",
    "plans": {
        "monthly": {"name": "חודשי", "days": 30, "price": "29.90"},
        "quarterly": {"name": "רבעוני", "days": 90, "price": "79.90"},
        "yearly": {"name": "שנתי", "days": 365, "price": "249.90"}
    }
}

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS vip_users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        expiry_date TEXT,
        approved_date TEXT,
        approved_by INTEGER,
        plan_type TEXT,
        group_added INTEGER DEFAULT 0,
        group_removed INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        first_name TEXT,
        photo_file_id TEXT,
        sent_date TEXT,
        plan_type TEXT,
        status TEXT DEFAULT 'pending'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_name TEXT,
        season INTEGER,
        episode INTEGER,
        title TEXT,
        file_id TEXT,
        duration TEXT,
        upload_date TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS group_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        action_date TEXT,
        reason TEXT
    )""")
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_FILE)

def is_vip(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM vip_users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if not result:
        return False
    expiry = datetime.datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
    return expiry > datetime.datetime.now()

def get_vip_expiry(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM vip_users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        expiry = datetime.datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        return expiry.strftime("%d/%m/%Y")
    return ""

def add_vip_user(user_id, username, first_name, days, plan_type, admin_id):
    expiry = datetime.datetime.now() + datetime.timedelta(days=days)
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO vip_users 
        (user_id, username, first_name, expiry_date, approved_date, approved_by, plan_type, group_added, group_removed)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)""",
        (user_id, username, first_name, expiry.strftime("%Y-%m-%d %H:%M:%S"),
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admin_id, plan_type))
    conn.commit()
    conn.close()
    return expiry

def get_pending_payments():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM pending_payments WHERE status = 'pending' ORDER BY sent_date")
    results = c.fetchall()
    conn.close()
    return results

def save_pending_payment(user_id, username, first_name, photo_file_id, plan_type):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO pending_payments 
        (user_id, username, first_name, photo_file_id, sent_date, plan_type)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, first_name, photo_file_id,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), plan_type))
    conn.commit()
    conn.close()

def approve_payment(payment_id, admin_id, days):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, plan_type FROM pending_payments WHERE id = ?", (payment_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return None
    user_id, username, first_name, plan_type = result
    c.execute("UPDATE pending_payments SET status = 'approved' WHERE id = ?", (payment_id,))
    conn.commit()
    expiry = add_vip_user(user_id, username, first_name, days, plan_type, admin_id)
    conn.close()
    return user_id, expiry

def reject_payment(payment_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE pending_payments SET status = 'rejected' WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()

def get_expired_vips():
    conn = get_db()
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT user_id FROM vip_users WHERE expiry_date < ? AND group_added = 1 AND group_removed = 0", (now,))
    results = c.fetchall()
    conn.close()
    return [r[0] for r in results]

def mark_user_removed(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE vip_users SET group_removed = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def mark_user_added(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE vip_users SET group_added = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

async def add_user_to_group(bot, user_id, group_id):
    try:
        await bot.unban_chat_member(group_id, user_id)
        return True
    except Exception as e:
        print(f"Error adding: {e}")
        return False

async def remove_user_from_group(bot, user_id, group_id):
    try:
        await bot.ban_chat_member(group_id, user_id)
        await bot.unban_chat_member(group_id, user_id)
        return True
    except Exception as e:
        print(f"Error removing: {e}")
        return False

async def send_group_invite(bot, user_id, group_id):
    try:
        invite = await bot.create_chat_invite_link(
            group_id,
            member_limit=1,
            expire_date=datetime.datetime.now() + datetime.timedelta(hours=24)
        )
        return invite.invite_link
    except Exception as e:
        print(f"Error invite: {e}")
        return None

def build_welcome_message(settings):
    plans = settings["plans"]
    plans_text = ""
    for key, plan in plans.items():
        plans_text += f"• {plan['name']} — ₪{plan['price']}\n"
    return settings["welcome_message"] + f"\n\nמחירים:\n{plans_text}"

def build_payment_details(settings):
    text = "פרטי תשלום לרכישת VIP\n\n"
    if settings.get("bit_link"):
        text += f"Bit:\n{settings['bit_link']}\n\n"
    if settings.get("paybox_link"):
        text += f"PayBox:\n{settings['paybox_link']}\n\n"
    if settings.get("paypal_email"):
        text += f"PayPal: {settings['paypal_email']}\n\n"
    text += "מחירים:\n"
    for key, plan in settings["plans"].items():
        text += f"• {plan['name']} — ₪{plan['price']}\n"
    text += "\nלאחר התשלום שלח צילום מסך של ההעברה"
    return text
    elif data == "admin_pending":
        if user_id != ADMIN_ID:
            return
        pending = get_pending_payments()
        if not pending:
            await query.edit_message_text("אין בקשות ממתינות!")
            return
        for p in pending:
            p_id, uid, uname, fname, photo_id, sent_date, plan, status = p
            display_name = fname or uname or f"משתמש {uid}"
            caption = f"בקשת VIP #{p_id}\n\n👤 משתמש: {display_name}\n🆔 ID: {uid}\n📅 נשלח: {sent_date}\n📦 חבילה: {plan}"
            keyboard = [[
                InlineKeyboardButton(f"✅ אשר #{p_id}", callback_data=f"approve_{p_id}"),
                InlineKeyboardButton(f"❌ דחה #{p_id}", callback_data=f"reject_{p_id}")
            ]]
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        await query.edit_message_text(
            f"⏳ נשלחו {len(pending)} בקשות עם תמונות למעלה 👆\n\nבחר אשר או דחה לכל בקשה"
        )
    elif data.startswith("approve_"):
        if user_id != ADMIN_ID:
            return
        payment_id = int(data.replace("approve_", ""))
        keyboard = [
            [InlineKeyboardButton("30 ימים", callback_data=f"confirm_approve_{payment_id}_30")],
            [InlineKeyboardButton("90 ימים", callback_data=f"confirm_approve_{payment_id}_90")],
            [InlineKeyboardButton("365 ימים", callback_data=f"confirm_approve_{payment_id}_365")],
            [InlineKeyboardButton("ביטול", callback_data="admin_pending")]
        ]
        await query.edit_message_text("בחר משך מנוי:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("confirm_approve_"):
        if user_id != ADMIN_ID:
            return
        parts = data.split("_")
        payment_id = int(parts[2])
        days = int(parts[3])
        result = approve_payment(payment_id, user_id, days)
        if result:
            target_user_id, expiry = result
            added = await add_user_to_group(bot, target_user_id, VIP_GROUP_ID)
            if added:
                mark_user_added(target_user_id)
            await bot.send_message(
                chat_id=target_user_id,
                text=f"מזל טוב! המנוי שלך אושר!\n\nקיבלת גישת VIP מלאה\nבתוקף עד: {expiry.strftime('%d/%m/%Y')}\n\n{'נוספת לקבוצת VIP' if added else ''}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("קישור לקבוצה", callback_data="group_link")]])
            )
            await query.edit_message_text(
                f"בקשה #{payment_id} אושרה!\nמשתמש: {target_user_id}\nבתוקף עד: {expiry.strftime('%d/%m/%Y')}"
            )
        else:
            await query.edit_message_text("שגיאה באישור")
    elif data.startswith("reject_"):
        if user_id != ADMIN_ID:
            return
        payment_id = int(data.replace("reject_", ""))
        reject_payment(payment_id)
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM pending_payments WHERE id = ?", (payment_id,))
        result = c.fetchone()
        conn.close()
        if result:
            await bot.send_message(chat_id=result[0], text="הבקשה שלך נדחתה")
        await query.edit_message_text(f"בקשה #{payment_id} נדחתה")
    elif data == "admin_check_expired":
        if user_id != ADMIN_ID:
            return
        expired = get_expired_vips()
        removed_count = 0
        for uid in expired:
            removed = await remove_user_from_group(bot, uid, VIP_GROUP_ID)
            if removed:
                mark_user_removed(uid)
                removed_count += 1
                try:
                    await bot.send_message(chat_id=uid, text="המנוי שלך פג! הוסרת מקבוצת VIP.\nלחידוש לחץ /start")
                except:
                    pass
        await query.edit_message_text(f"בדיקה הושלמה!\nנמצאו: {len(expired)}\nהוסרו: {removed_count}")

async def handle_photo(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    if not context.user_data.get("awaiting_payment_proof"):
        await update.message.reply_text("אין בקשה פתוחה. לחץ על רכוש VIP כדי להתחיל.")
        return
    plan = context.user_data.get("selected_plan", "monthly")
    photo_file_id = update.message.photo[-1].file_id
    save_pending_payment(user_id, username, first_name, photo_file_id, plan)
    context.user_data["awaiting_payment_proof"] = False
    await update.message.reply_text("ההוכחה נשלחה לאדמין!\n\nאנא המתן לאישור...")
    plans_names = {k: v["name"] for k, v in load_settings()["plans"].items()}
    plan_name = plans_names.get(plan, plan)
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"בקשת VIP חדשה!\nמשתמש: {first_name or username or user_id}\nID: {user_id}\nחבילה: {plan_name}\n\nלחץ /admin כדי לאשר"
    )

async def check_expired_job(context):
    print(f"בודק מנויים שפגו... {datetime.datetime.now()}")
    expired = get_expired_vips()
    for uid in expired:
        removed = await remove_user_from_group(context.bot, uid, VIP_GROUP_ID)
        if removed:
            mark_user_removed(uid)
            try:
                await context.bot.send_message(chat_id=uid, text="המנוי שלך פג! הוסרת מקבוצת VIP.")
            except:
                pass

def main():
    init_db()
    load_settings()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    job_queue = app.job_queue
    job_queue.run_repeating(check_expired_job, interval=3600, first=10)
    print("הבוט רץ!")
    print("שלח /start בטלגרם")
    print("שלח /admin לפאנל ניהול")
    app.run_polling()

if __name__ == "__main__":
    main()

async def handle_text(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    settings = load_settings()
    if user_id != ADMIN_ID:
        return
    editing = context.user_data.get("editing")
    editing_plan = context.user_data.get("editing_plan")
    if editing in ["bit", "paybox", "paypal"]:
        if editing == "bit":
            settings["bit_link"] = text
        elif editing == "paybox":
            settings["paybox_link"] = text
        elif editing == "paypal":
            settings["paypal_email"] = text
        save_settings(settings)
        context.user_data["editing"] = None
        await update.message.reply_text(
            f"{editing.title()} עודכן בהצלחה!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("חזור להגדרות", callback_data="admin_settings")]])
        )
        return
    if editing_plan:
        try:
            parts = text.split("|")
            if len(parts) == 3:
                name, price, days = parts
                settings["plans"][editing_plan] = {
                    "name": name.strip(),
                    "price": price.strip(),
                    "days": int(days.strip())
                }
                save_settings(settings)
                context.user_data["editing_plan"] = None
                await update.message.reply_text(
                    f"חבילה עודכנה!\n\nשם: {name}\nמחיר: ₪{price}\nימים: {days}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("חזור למחירים", callback_data="set_prices")]])
                )
            else:
                await update.message.reply_text("פורמט שגוי! השתמש ב: שם|מחיר|ימים")
        except:
            await update.message.reply_text("שגיאה! ודא שהמחיר ומספר הימים הם מספרים.")
        return
    if context.user_data.get("editing_welcome"):
        settings["welcome_message"] = text
        save_settings(settings)
        context.user_data["editing_welcome"] = False
        await update.message.reply_text(
            "הודעת פתיחה עודכנה!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("חזור להגדרות", callback_data="admin_settings")]])
        )
        return
    if context.user_data.get("editing_support"):
        settings["support_username"] = text.replace("@", "")
        save_settings(settings)
        context.user_data["editing_support"] = False
        await update.message.reply_text(
            f"תמיכה עודכנה!\nמשתמש: @{settings['support_username']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("חזור להגדרות", callback_data="admin_settings")]])
        )
        return

async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    bot = context.bot
    settings = load_settings()
    if data == "admin_settings":
        await settings_panel(update, context)
        return
    elif data == "set_payment_links":
        await settings_payment_links(update, context)
        return
    elif data in ["edit_bit", "edit_paybox", "edit_paypal"]:
        await edit_payment_link(update, context)
        return
    elif data == "set_prices":
        await settings_prices(update, context)
        return
    elif data.startswith("edit_plan_"):
        await edit_plan(update, context)
        return
    elif data == "set_welcome":
        context.user_data["editing_welcome"] = True
        await query.edit_message_text("עריכת הודעת פתיחה\n\nשלח לי את הטקסט החדש:")
        return
    elif data == "set_support":
        context.user_data["editing_support"] = True
        await query.edit_message_text("עדכן משתמש תמיכה\n\nשלח לי את שם המשתמש (ללא @):")
        return
    elif data == "admin_back":
        await admin_panel(update, context)
        return
    if data == "buy_vip":
        plans = settings["plans"]
        keyboard = []
        for key, plan in plans.items():
            keyboard.append([InlineKeyboardButton(
                f"{plan['name']} — ₪{plan['price']}",
                callback_data=f"plan_{key}"
            )])
        keyboard.append([InlineKeyboardButton("חזור", callback_data="back_start")])
        await query.edit_message_text("בחר את חבילת ה-VIP שלך:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("plan_"):
        plan = data.replace("plan_", "")
        context.user_data["selected_plan"] = plan
        plan_data = settings["plans"][plan]
        keyboard = [
            [InlineKeyboardButton("שלחתי תשלום", callback_data="sent_payment")],
            [InlineKeyboardButton("חזור", callback_data="buy_vip")]
        ]
        payment_text = build_payment_details(settings)
        await query.edit_message_text(
            f"חבילה נבחרה: {plan_data['name']}\nמחיר: ₪{plan_data['price']}\nמשך: {plan_data['days']} ימים\n\n{payment_text}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "sent_payment":
        await query.edit_message_text("שלח עכשיו צילום מסך של ההעברה\n\nהאדמין יבדוק ויאשר את הבקשה בהקדם.")
        context.user_data["awaiting_payment_proof"] = True
    elif data == "group_link":
        if not is_vip(user_id):
            await query.edit_message_text("נדרש מנוי VIP!")
            return
        link = await send_group_invite(bot, user_id, VIP_GROUP_ID)
        if link:
            keyboard = [[InlineKeyboardButton("הצטרף לקבוצה", url=link)]]
            await query.edit_message_text("קישור לקבוצת VIP\n\nהקישור תקף ל-24 שעות.", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("שגיאה ביצירת הקישור.")
    elif data == "my_status":
        if is_vip(user_id):
            expiry = get_vip_expiry(user_id)
            keyboard = [[InlineKeyboardButton("חזור", callback_data="back_start")]]
            await query.edit_message_text(f"פרטי מנוי VIP\n\nבתוקף עד: {expiry}", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("אין לך מנוי VIP פעיל.")
    elif data == "support":
        support = settings.get("support_username", "your_username")
        await query.edit_message_text(f"תמיכה\n\n@{support}\n\nשעות פעילות: 24/7")
    elif data == "back_start":
        await start(update, context)

async def start(update, context):
    settings = load_settings()
    user_id = update.effective_user.id
    if is_vip(user_id):
        keyboard = [
            [InlineKeyboardButton("צפה בפרקים", callback_data="browse_series")],
            [InlineKeyboardButton("קישור לקבוצת VIP", callback_data="group_link")],
            [InlineKeyboardButton("פרטי מנוי", callback_data="my_status")],
            [InlineKeyboardButton("תמיכה", callback_data="support")]
        ]
        expiry = get_vip_expiry(user_id)
        text = f"מזל טוב! המנוי שלך אושר!\n\nקיבלת גישת VIP מלאה\nהמנוי בתוקף עד: {expiry}"
    else:
        keyboard = [
            [InlineKeyboardButton("רכוש VIP", callback_data="buy_vip")],
            [InlineKeyboardButton("צור קשר", callback_data="support")],
            [InlineKeyboardButton("שאלות נפוצות", callback_data="faq")]
        ]
        text = build_welcome_message(settings)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_panel(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("אין לך הרשאות גישה!")
        return
    pending = get_pending_payments()
    keyboard = [
        [InlineKeyboardButton(f"בקשות ממתינות ({len(pending)})", callback_data="admin_pending")],
        [InlineKeyboardButton("הגדרות בוט", callback_data="admin_settings")],
        [InlineKeyboardButton("הוסף VIP ידני", callback_data="admin_add_manual")],
        [InlineKeyboardButton("רשימת VIP פעילים", callback_data="admin_list_vip")],
        [InlineKeyboardButton("בדוק מנויים שפגו", callback_data="admin_check_expired")]
    ]
    await update.message.reply_text("פאנל ניהול", reply_markup=InlineKeyboardMarkup(keyboard))

async def settings_panel(update, context):
    query = update.callback_query
    await query.answer()
    settings = load_settings()
    text = "הגדרות בוט\n\n"
    text += f"Bit: {settings.get('bit_link', 'לא מוגדר')[:40]}\n"
    text += f"PayBox: {settings.get('paybox_link', 'לא מוגדר')[:40]}\n"
    text += f"PayPal: {settings.get('paypal_email', 'לא מוגדר')}\n"
    text += f"תמיכה: @{settings.get('support_username', 'לא מוגדר')}\n\n"
    text += "חבילות:\n"
    for key, plan in settings["plans"].items():
        text += f"• {plan['name']}: ₪{plan['price']} ({plan['days']} ימים)\n"
    keyboard = [
        [InlineKeyboardButton("עדכן קישורי תשלום", callback_data="set_payment_links")],
        [InlineKeyboardButton("עדכן מחירים", callback_data="set_prices")],
        [InlineKeyboardButton("עדכן הודעת פתיחה", callback_data="set_welcome")],
        [InlineKeyboardButton("עדכן תמיכה", callback_data="set_support")],
        [InlineKeyboardButton("חזור", callback_data="admin_back")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def settings_payment_links(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("עדכן Bit", callback_data="edit_bit")],
        [InlineKeyboardButton("עדכן PayBox", callback_data="edit_paybox")],
        [InlineKeyboardButton("עדכן PayPal", callback_data="edit_paypal")],
        [InlineKeyboardButton("חזור", callback_data="admin_settings")]
    ]
    await query.edit_message_text("עדכון קישורי תשלום\n\nבחר איזה קישור לעדכן:", reply_markup=InlineKeyboardMarkup(keyboard))

async def edit_payment_link(update, context):
    query = update.callback_query
    await query.answer()
    link_type = query.data.replace("edit_", "")
    context.user_data["editing"] = link_type
    names = {"bit": "Bit", "paybox": "PayBox", "paypal": "PayPal"}
    await query.edit_message_text(f"עדכון {names.get(link_type, link_type)}\n\nשלח לי עכשיו את הערך החדש:")

async def settings_prices(update, context):
    query = update.callback_query
    await query.answer()
    settings = load_settings()
    keyboard = []
    for key, plan in settings["plans"].items():
        keyboard.append([InlineKeyboardButton(
            f"{plan['name']}: ₪{plan['price']} ({plan['days']} ימים)",
            callback_data=f"edit_plan_{key}"
        )])
    keyboard.append([InlineKeyboardButton("חזור", callback_data="admin_settings")])
    await query.edit_message_text("ניהול מחירים\n\nבחר חבילה לעריכה:", reply_markup=InlineKeyboardMarkup(keyboard))

async def edit_plan(update, context):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.replace("edit_plan_", "")
    context.user_data["editing_plan"] = plan_key
    await query.edit_message_text("עריכת חבילה\n\nשלח לי בפורמט:\nשם|מחיר|ימים\n\nלדוגמה: חודשי|29.90|30")    bot.send_message(message.chat.id, "ההודעה שלך הועברה בהצלחה. נחזור אליך בהקדם.")

@bot.message_handler(content_types=['photo'])
def handle_docs_photo(message):
    bot.send_message(message.chat.id, "צילום המסך התקבל והועבר לאישור. נשלח לך קישור ברגע שהתשלום יאושר.")
    
    markup = InlineKeyboardMarkup()
    btn_approve = InlineKeyboardButton("אישור תשלום", callback_data=f"approve_{message.from_user.id}")
    btn_reject = InlineKeyboardButton("דחיית תשלום", callback_data=f"reject_{message.from_user.id}")
    markup.add(btn_approve, btn_reject)
    
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"צילום מסך לתשלום ממשתמש @{message.from_user.username} (מזהה: {message.from_user.id})", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('reject_'))
def handle_admin_approval(call):
    action, user_id = call.data.split('_')
    user_id = int(user_id)
    
    if action == 'approve':
        try:
            invite_link = bot.create_chat_invite_link(chat_id=GROUP_ID, member_limit=1).invite_link
            bot.send_message(user_id, f"התשלום אושר! הנה קישור ההצטרפות שלך לקבוצה:\n{invite_link}")
            bot.edit_message_caption(caption="התשלום אושר וקישור נשלח למשתמש בהצלחה.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception as e:
            bot.send_message(ADMIN_ID, "שגיאה ביצירת קישור. חשוב לוודא שהבוט מוגדר כמנהל בקבוצה ויש לו הרשאה להוסיף משתמשים.")
    
    elif action == 'reject':
        bot.send_message(user_id, "לצערנו התשלום לא אושר. אנא פנו לעזרה אם מדובר בטעות.")
        bot.edit_message_caption(caption="התשלום נדחה והמשתמש עודכן.", chat_id=call.message.chat.id, message_id=call.message.message_id)

bot.polling(none_stop=True)
bot.remove_webhook()
bot.polling(none_stop=True)
