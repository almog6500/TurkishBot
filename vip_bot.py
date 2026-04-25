"""
VIP Telegram Bot — Production Ready
שלח /admin לבוט בפרטי לתפריט ניהול
"""

import json, logging, sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN     = "8538355821:AAE6u-r4BlTKrGzOQVSvE1rzgJQNbvUBIcU"
ADMIN_CHAT_ID = 217420509
VIP_GROUP_ID  = -1003803654378
SETTINGS_FILE = "settings.json"
DB_FILE       = "vip_bot.db"
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── Settings ──────────────────────────────────────────────────────────────────
def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"welcome_message": "ברוך הבא!", "plans": []}

def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def get_welcome():
    return load_settings().get("welcome_message", "ברוך הבא!")

def get_plans():
    return load_settings().get("plans", [])

def plan_label(p):
    return f"{p['name']} — {p['price']}₪"


# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_FILE)
    con.execute("""CREATE TABLE IF NOT EXISTS pending (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        plan TEXT, screenshot_file_id TEXT, submitted_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        plan TEXT, expires_at TEXT, joined_at TEXT)""")
    con.commit(); con.close()

def db_save_pending(user_id, username, full_name, plan, file_id):
    con = sqlite3.connect(DB_FILE)
    con.execute("INSERT OR REPLACE INTO pending VALUES (?,?,?,?,?,?)",
        (user_id, username, full_name, plan, file_id, datetime.now().isoformat()))
    con.commit(); con.close()

def db_get_pending(user_id=None):
    con = sqlite3.connect(DB_FILE)
    if user_id:
        row = con.execute("SELECT * FROM pending WHERE user_id=?", (user_id,)).fetchone()
        con.close(); return row
    rows = con.execute("SELECT * FROM pending ORDER BY submitted_at DESC").fetchall()
    con.close(); return rows

def db_remove_pending(user_id):
    con = sqlite3.connect(DB_FILE)
    con.execute("DELETE FROM pending WHERE user_id=?", (user_id,))
    con.commit(); con.close()

def db_save_member(user_id, username, full_name, plan, days):
    expires = (datetime.now() + timedelta(days=days)).isoformat()
    con = sqlite3.connect(DB_FILE)
    con.execute("INSERT OR REPLACE INTO members VALUES (?,?,?,?,?,?)",
        (user_id, username, full_name, plan, expires, datetime.now().isoformat()))
    con.commit(); con.close()
    return expires

def db_get_members():
    con = sqlite3.connect(DB_FILE)
    rows = con.execute("SELECT * FROM members ORDER BY expires_at ASC").fetchall()
    con.close(); return rows

def db_remove_member(user_id):
    con = sqlite3.connect(DB_FILE)
    con.execute("DELETE FROM members WHERE user_id=?", (user_id,))
    con.commit(); con.close()

def db_count_members():
    con = sqlite3.connect(DB_FILE)
    c = con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    con.close(); return c

def db_count_pending():
    con = sqlite3.connect(DB_FILE)
    c = con.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
    con.close(); return c


# ── Helpers ───────────────────────────────────────────────────────────────────
def is_admin(update: Update):
    return update.effective_user.id == ADMIN_CHAT_ID

def build_plans_keyboard():
    plans = get_plans()
    if not plans:
        return InlineKeyboardMarkup([[InlineKeyboardButton("אין חבילות זמינות", callback_data="noop")]])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(plan_label(p), callback_data=f"plan:{i}")]
        for i, p in enumerate(plans)
    ])


# ── אישור/דחייה — פונקציה משותפת ─────────────────────────────────────────────
async def do_approve(user_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> str:
    """מאשר משתמש, שולח קישור, מחזיר תיאור לתצוגה"""
    row = db_get_pending(user_id)
    if not row:
        return None
    _, username, full_name, plan_str, _, _ = row
    plans = get_plans()
    days = next((int(p.get("days", 30)) for p in plans if plan_label(p) == plan_str), 30)
    expires = db_save_member(user_id, username, full_name, plan_str, days)
    db_remove_pending(user_id)
    expire_str = datetime.fromisoformat(expires).strftime("%d/%m/%Y")
    try:
        invite = await ctx.bot.create_chat_invite_link(
            chat_id=VIP_GROUP_ID, member_limit=1,
            expire_date=datetime.now() + timedelta(hours=24), name=f"VIP-{user_id}")
        await ctx.bot.send_message(
            user_id,
            f"🎉 *אושרת לקבוצת ה-VIP!*\n\n📦 {plan_str}\n📅 עד: {expire_str}\n\n👇 קישור לקבוצה:\n{invite.invite_link}\n\nמחכים לך! ❤️",
            parse_mode="Markdown"
        )
    except Exception as e:
        await ctx.bot.send_message(user_id, f"🎉 אושרת! עד {expire_str}. האדמין ישלח קישור בקרוב.")
        log.error(f"Invite error: {e}")
    return f"✅ אושר — {full_name} | עד {expire_str}"


async def do_reject(user_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> str:
    """דוחה משתמש, מחזיר תיאור לתצוגה"""
    row = db_get_pending(user_id)
    if not row:
        return None
    _, _, full_name, _, _, _ = row
    db_remove_pending(user_id)
    await ctx.bot.send_message(user_id, "❌ הבקשה לא אושרה. שלח שוב אם מדובר בטעות.")
    return f"❌ נדחה — {full_name}"


# ════════════════════════════════════════════════════════════════════════════════
#  תפריט אדמין
# ════════════════════════════════════════════════════════════════════════════════

def admin_main_keyboard():
    pending = db_count_pending()
    members = db_count_members()
    pending_label = f"⏳ בקשות ממתינות ({pending}) 🔴" if pending > 0 else "⏳ בקשות ממתינות"
    return (
        f"👑 *תפריט ניהול VIP*\n\n"
        f"👥 חברים פעילים: *{members}*\n"
        f"⏳ ממתינים לאישור: *{pending}*\n\n"
        f"בחר פעולה:",
        InlineKeyboardMarkup([
            [InlineKeyboardButton(pending_label, callback_data="admin:pending")],
            [InlineKeyboardButton("👥 חברים פעילים", callback_data="admin:members")],
            [InlineKeyboardButton("📦 ניהול חבילות", callback_data="admin:plans")],
            [InlineKeyboardButton("✏️ הודעת פתיחה", callback_data="admin:welcome")],
            [InlineKeyboardButton("📢 שליחת הודעה לכולם", callback_data="admin:broadcast")],
        ])
    )


def pending_menu_content():
    """בונה את תוכן תפריט הבקשות הממתינות"""
    rows = db_get_pending()
    if not rows:
        return (
            "✅ *אין בקשות ממתינות*\nכולם טופלו!",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="admin:home")]])
        )
    text = f"⏳ *בקשות ממתינות ({len(rows)}):*\n\n"
    buttons = []
    for row in rows:
        user_id, username, full_name, plan, file_id, submitted_at = row
        text += f"👤 *{full_name}*\n📱 @{username or '-'} | 🆔 `{user_id}`\n📦 {plan}\n\n"
        buttons.append([
            InlineKeyboardButton(f"✅ אשר — {full_name}", callback_data=f"adm_approve:{user_id}"),
            InlineKeyboardButton(f"❌ דחה", callback_data=f"adm_reject:{user_id}"),
        ])
        # כפתור לצפייה בתמונה
        buttons.append([
            InlineKeyboardButton(f"🖼 הצג צילום מסך", callback_data=f"adm_photo:{user_id}"),
        ])
    buttons.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="admin:home")])
    return text, InlineKeyboardMarkup(buttons)


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    text, keyboard = admin_main_keyboard()
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def cb_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.answer("אין הרשאה", show_alert=True); return
    await query.answer()
    data = query.data

    # ── תפריט ראשי ──
    if data == "admin:home":
        text, keyboard = admin_main_keyboard()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # ── בקשות ממתינות ──
    elif data == "admin:pending":
        text, keyboard = pending_menu_content()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # ── אישור מתוך תפריט ──
    elif data.startswith("adm_approve:"):
        user_id = int(data.split(":")[-1])
        result = await do_approve(user_id, ctx)
        await query.answer(result or "לא נמצאה בקשה", show_alert=True)
        # רענן את תפריט הממתינים
        text, keyboard = pending_menu_content()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # ── דחייה מתוך תפריט ──
    elif data.startswith("adm_reject:"):
        user_id = int(data.split(":")[-1])
        result = await do_reject(user_id, ctx)
        await query.answer(result or "לא נמצאה בקשה", show_alert=True)
        text, keyboard = pending_menu_content()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # ── הצגת צילום מסך ──
    elif data.startswith("adm_photo:"):
        user_id = int(data.split(":")[-1])
        row = db_get_pending(user_id)
        if row:
            _, username, full_name, plan, file_id, _ = row
            await ctx.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=file_id,
                caption=f"🖼 צילום מסך של {full_name}\n📦 {plan}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ אשר", callback_data=f"adm_approve:{user_id}"),
                    InlineKeyboardButton("❌ דחה", callback_data=f"adm_reject:{user_id}"),
                ]])
            )
        else:
            await query.answer("לא נמצא צילום מסך", show_alert=True)

    # ── חברים פעילים ──
    elif data == "admin:members":
        rows = db_get_members()
        if not rows:
            await query.edit_message_text("👥 *אין חברים פעילים כרגע*", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזרה", callback_data="admin:home")]]))
            return
        text = f"👥 *חברים פעילים ({len(rows)}):*\n\n"
        buttons = []
        for row in rows:
            uid, username, full_name, plan, expires_at, _ = row
            days = max(0, (datetime.fromisoformat(expires_at) - datetime.now()).days)
            expire_str = datetime.fromisoformat(expires_at).strftime("%d/%m/%Y")
            icon = "🔴" if days < 7 else "🟢"
            text += f"{icon} *{full_name}* (@{username or '-'})\n📦 {plan} | עד {expire_str} ({days} ימים)\n🆔 `{uid}`\n\n"
            buttons.append([InlineKeyboardButton(f"🗑 הסר — {full_name}", callback_data=f"kick:{uid}")])
        buttons.append([InlineKeyboardButton("🔙 חזרה", callback_data="admin:home")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    # ── ניהול חבילות ──
    elif data == "admin:plans":
        await show_plans_menu(query)

    elif data.startswith("admin:delplan:"):
        idx = int(data.split(":")[-1])
        s = load_settings()
        if idx < len(s["plans"]):
            removed = s["plans"].pop(idx)
            save_settings(s)
            await query.answer(f"✅ נמחקה: {removed['name']}", show_alert=True)
        await show_plans_menu(query)

    elif data.startswith("admin:setlink:"):
        idx = int(data.split(":")[-1])
        ctx.user_data["editing_plan_idx"] = idx
        ctx.user_data["admin_action"] = "wait_link"
        plans = get_plans()
        name = plans[idx]["name"] if idx < len(plans) else ""
        await query.edit_message_text(
            f"🔗 *שינוי קישור תשלום*\nחבילה: *{name}*\n\nשלח את הקישור החדש:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול", callback_data="admin:plans")]])
        )

    elif data == "admin:addplan":
        ctx.user_data["admin_action"] = "wait_plan_name"
        ctx.user_data["new_plan"] = {}
        await query.edit_message_text(
            "➕ *הוספת חבילה חדשה*\n\nשלח את *שם החבילה*:\nלדוגמה: גישה חודשית",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול", callback_data="admin:plans")]])
        )

    # ── הודעת פתיחה ──
    elif data == "admin:welcome":
        current = get_welcome()
        ctx.user_data["admin_action"] = "wait_welcome"
        await query.edit_message_text(
            f"✏️ *עריכת הודעת פתיחה*\n\n*נוכחית:*\n{current}\n\n─────────\nשלח את הטקסט החדש:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול", callback_data="admin:home")]])
        )

    # ── שליחה לכולם ──
    elif data == "admin:broadcast":
        ctx.user_data["admin_action"] = "wait_broadcast"
        await query.edit_message_text(
            "📢 *שליחת הודעה לכל החברים*\n\nשלח את ההודעה:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול", callback_data="admin:home")]])
        )


async def show_plans_menu(query):
    plans = get_plans()
    text = "📦 *ניהול חבילות:*\n\n"
    buttons = []
    if plans:
        for i, p in enumerate(plans, 1):
            link = p.get("payment_link", "")
            text += f"*{i}.* {plan_label(p)} | {p['days']} ימים\n🔗 {link or 'ללא קישור'}\n\n"
            buttons.append([
                InlineKeyboardButton(f"🔗 שנה קישור", callback_data=f"admin:setlink:{i-1}"),
                InlineKeyboardButton(f"🗑 מחק", callback_data=f"admin:delplan:{i-1}"),
            ])
    else:
        text += "אין חבילות עדיין.\n\n"
    buttons.append([InlineKeyboardButton("➕ הוסף חבילה", callback_data="admin:addplan")])
    buttons.append([InlineKeyboardButton("🔙 חזרה", callback_data="admin:home")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── הסרת חבר ──────────────────────────────────────────────────────────────────
async def cb_kick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.answer("אין הרשאה", show_alert=True); return
    await query.answer()
    user_id = int(query.data.split(":")[-1])
    try:
        await ctx.bot.ban_chat_member(VIP_GROUP_ID, user_id)
        await ctx.bot.unban_chat_member(VIP_GROUP_ID, user_id)
        await ctx.bot.send_message(user_id, "⏰ *המנוי שלך הסתיים.*\nלחדש: /start", parse_mode="Markdown")
    except Exception as e:
        log.error(f"Kick error: {e}")
    db_remove_member(user_id)
    await query.answer("✅ החבר הוסר", show_alert=True)
    # רענן רשימת חברים
    rows = db_get_members()
    if not rows:
        await query.edit_message_text("👥 *אין חברים פעילים כרגע*", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזרה", callback_data="admin:home")]]))
        return
    text = f"👥 *חברים פעילים ({len(rows)}):*\n\n"
    buttons = []
    for row in rows:
        uid, username, full_name, plan, expires_at, _ = row
        days = max(0, (datetime.fromisoformat(expires_at) - datetime.now()).days)
        expire_str = datetime.fromisoformat(expires_at).strftime("%d/%m/%Y")
        icon = "🔴" if days < 7 else "🟢"
        text += f"{icon} *{full_name}* (@{username or '-'})\n📦 {plan} | עד {expire_str} ({days} ימים)\n🆔 `{uid}`\n\n"
        buttons.append([InlineKeyboardButton(f"🗑 הסר — {full_name}", callback_data=f"kick:{uid}")])
    buttons.append([InlineKeyboardButton("🔙 חזרה", callback_data="admin:home")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── אישור/דחייה ישירות מהתמונה שנשלחת לאדמין ────────────────────────────────
async def cb_approve_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.answer("אין הרשאה!", show_alert=True); return
    await query.answer()
    action, uid_str = query.data.split(":")
    user_id = int(uid_str)

    if action == "approve":
        result = await do_approve(user_id, ctx)
        await query.edit_message_caption(result or "הבקשה כבר טופלה")
    elif action == "reject":
        result = await do_reject(user_id, ctx)
        await query.edit_message_caption(result or "הבקשה כבר טופלה")


# ── קבלת טקסט מהאדמין ────────────────────────────────────────────────────────
async def handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    action = ctx.user_data.get("admin_action")
    if not action: return
    text = update.message.text.strip()

    if action == "wait_welcome":
        s = load_settings()
        s["welcome_message"] = text
        save_settings(s)
        ctx.user_data.pop("admin_action", None)
        await update.message.reply_text(f"✅ *הודעת הפתיחה עודכנה!*", parse_mode="Markdown")
        t, kb = admin_main_keyboard()
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=kb)

    elif action == "wait_link":
        idx = ctx.user_data.get("editing_plan_idx", 0)
        s = load_settings()
        if idx < len(s["plans"]):
            s["plans"][idx]["payment_link"] = text
            save_settings(s)
            await update.message.reply_text(f"✅ *הקישור עודכן!*\n🔗 {text}", parse_mode="Markdown")
        ctx.user_data.pop("admin_action", None)
        ctx.user_data.pop("editing_plan_idx", None)
        # חזרה לתפריט חבילות
        plans = get_plans()
        menu_text = "📦 *ניהול חבילות:*\n\n"
        buttons = []
        for i, p in enumerate(plans, 1):
            link = p.get("payment_link", "")
            menu_text += f"*{i}.* {plan_label(p)} | {p['days']} ימים\n🔗 {link or 'ללא קישור'}\n\n"
            buttons.append([
                InlineKeyboardButton(f"🔗 שנה קישור", callback_data=f"admin:setlink:{i-1}"),
                InlineKeyboardButton(f"🗑 מחק", callback_data=f"admin:delplan:{i-1}"),
            ])
        buttons.append([InlineKeyboardButton("➕ הוסף חבילה", callback_data="admin:addplan")])
        buttons.append([InlineKeyboardButton("🔙 חזרה", callback_data="admin:home")])
        await update.message.reply_text(menu_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "wait_plan_name":
        ctx.user_data["new_plan"]["name"] = text
        ctx.user_data["admin_action"] = "wait_plan_price"
        await update.message.reply_text(f"✅ שם: *{text}*\n\nשלח את *המחיר* (₪):", parse_mode="Markdown")

    elif action == "wait_plan_price":
        ctx.user_data["new_plan"]["price"] = text
        ctx.user_data["admin_action"] = "wait_plan_days"
        await update.message.reply_text(f"✅ מחיר: *{text}₪*\n\nשלח *כמה ימי גישה*:", parse_mode="Markdown")

    elif action == "wait_plan_days":
        ctx.user_data["new_plan"]["days"] = int(text) if text.isdigit() else 30
        ctx.user_data["admin_action"] = "wait_plan_link"
        await update.message.reply_text(f"✅ ימים: *{text}*\n\nשלח *קישור תשלום*\n(או שלח ❌ לדלג):", parse_mode="Markdown")

    elif action == "wait_plan_link":
        new_plan = ctx.user_data.get("new_plan", {})
        new_plan["payment_link"] = "" if text == "❌" else text
        s = load_settings()
        s["plans"].append(new_plan)
        save_settings(s)
        ctx.user_data.pop("admin_action", None)
        ctx.user_data.pop("new_plan", None)
        await update.message.reply_text(
            f"✅ *החבילה נוספה!*\n\n📦 {plan_label(new_plan)}\n⏱ {new_plan['days']} ימים\n🔗 {new_plan.get('payment_link') or 'ללא קישור'}",
            parse_mode="Markdown"
        )
        t, kb = admin_main_keyboard()
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=kb)

    elif action == "wait_broadcast":
        rows = db_get_members()
        success = 0
        for row in rows:
            try:
                await ctx.bot.send_message(row[0], f"📢 *הודעה מהאדמין:*\n\n{text}", parse_mode="Markdown")
                success += 1
            except Exception as e:
                log.warning(f"Broadcast failed {row[0]}: {e}")
        ctx.user_data.pop("admin_action", None)
        await update.message.reply_text(f"✅ נשלח ל-{success} חברים.")
        t, kb = admin_main_keyboard()
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════════════════════════════════════════
#  זרימת משתמש רגיל
# ════════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_welcome(), reply_markup=build_plans_keyboard())
    ctx.user_data["step"] = "choose_plan"


async def cb_plan_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "noop": return
    idx = int(query.data.replace("plan:", ""))
    plans = get_plans()
    if idx >= len(plans):
        await query.edit_message_text("החבילה כבר לא זמינה. שלח /start מחדש."); return
    plan = plans[idx]
    ctx.user_data["plan_label"] = plan_label(plan)
    ctx.user_data["step"] = "awaiting_screenshot"
    link = plan.get("payment_link", "")
    link_line = f"\n👉 [לחץ כאן לתשלום]({link})\n" if link else "\n"
    await query.edit_message_text(
        f"✅ בחרת: *{plan_label(plan)}*\n{link_line}\nלאחר התשלום, שלח *צילום מסך* של האישור כאן 📸",
        parse_mode="Markdown"
    )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_CHAT_ID: return

    if ctx.user_data.get("step") != "awaiting_screenshot" or not ctx.user_data.get("plan_label"):
        await update.message.reply_text("אנא לחץ /start ובחר חבילה תחילה."); return

    file_id = update.message.photo[-1].file_id
    plan_str = ctx.user_data["plan_label"]
    db_save_pending(user.id, user.username or "", user.full_name, plan_str, file_id)
    ctx.user_data["step"] = "pending_approval"

    # ✅ התראה מיידית לאדמין עם כפתורי אישור/דחייה על התמונה
    caption = (
        f"🔔 *בקשה חדשה!*\n\n"
        f"👤 {user.full_name}\n"
        f"📱 @{user.username or 'אין'}\n"
        f"🆔 `{user.id}`\n"
        f"📦 {plan_str}"
    )
    await ctx.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=file_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ אשר", callback_data=f"approve:{user.id}"),
            InlineKeyboardButton("❌ דחה",  callback_data=f"reject:{user.id}"),
        ]])
    )

    await update.message.reply_text(
        "📨 *התקבל!*\n⏳ ממתין לאישור — נעדכן אותך בקרוב 🙏",
        parse_mode="Markdown"
    )


# ── בדיקת פקיעת מנויים ───────────────────────────────────────────────────────
async def check_expirations(ctx: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().isoformat()
    con = sqlite3.connect(DB_FILE)
    expired = con.execute("SELECT user_id, full_name FROM members WHERE expires_at < ?", (now,)).fetchall()
    for (user_id, full_name) in expired:
        try:
            await ctx.bot.ban_chat_member(VIP_GROUP_ID, user_id)
            await ctx.bot.unban_chat_member(VIP_GROUP_ID, user_id)
            await ctx.bot.send_message(user_id, "⏰ *המנוי שלך פג תוקף.*\n\nלחדש: /start", parse_mode="Markdown")
            await ctx.bot.send_message(ADMIN_CHAT_ID, f"ℹ️ המנוי של {full_name} (`{user_id}`) פג — הוסר.", parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Could not remove {user_id}: {e}")
        con.execute("DELETE FROM members WHERE user_id=?", (user_id,))
    con.commit(); con.close()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # משתמש רגיל
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    app.add_handler(CallbackQueryHandler(cb_plan_chosen, pattern=r"^plan:"))

    # אדמין — תפריט כפתורים
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(cb_admin,         pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(cb_admin,         pattern=r"^adm_(approve|reject|photo):"))
    app.add_handler(CallbackQueryHandler(cb_kick,          pattern=r"^kick:"))
    app.add_handler(CallbackQueryHandler(cb_approve_reject, pattern=r"^(approve|reject):"))

    # טקסט מאדמין
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_CHAT_ID),
        handle_admin_text
    ))

    app.job_queue.run_repeating(check_expirations, interval=3600, first=30)

    log.info("✅ VIP Bot is running!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
