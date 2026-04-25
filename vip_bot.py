"""
VIP Telegram Bot — Production Ready
סדרות טורקיות VIP

פקודות אדמין (שלח לבוט בצ'אט הפרטי):
  /help                              — רשימת כל הפקודות
  /plans                             — הצגת החבילות הנוכחיות
  /setlink <קישור> [מספר חבילה]     — שינוי קישור תשלום
  /setwelcome <טקסט>                 — שינוי הודעת ברוכים הבאים
  /addplan <שם>|<מחיר>|<ימים>|<קישור>  — הוספת חבילה
  /delplan <מספר>                    — מחיקת חבילה
  /members                           — רשימת חברים פעילים
  /pending                           — בקשות ממתינות
  /approve <user_id>                 — אישור ידני
  /reject <user_id>                  — דחייה ידנית
  /kick <user_id>                    — הסרת חבר מהקבוצה
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
    except Exception as e:
        log.error(f"Could not load settings: {e}")
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


# ── Keyboard ──────────────────────────────────────────────────────────────────
def build_plans_keyboard():
    plans = get_plans()
    if not plans:
        return InlineKeyboardMarkup([[InlineKeyboardButton("אין חבילות זמינות", callback_data="noop")]])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(plan_label(p), callback_data=f"plan:{i}")]
        for i, p in enumerate(plans)
    ])


# ── User flow ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_welcome(), reply_markup=build_plans_keyboard())
    ctx.user_data["step"] = "choose_plan"


async def cb_plan_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "noop":
        return
    idx = int(query.data.replace("plan:", ""))
    plans = get_plans()
    if idx >= len(plans):
        await query.edit_message_text("החבילה כבר לא זמינה. שלח /start מחדש.")
        return
    plan = plans[idx]
    ctx.user_data["plan_idx"] = idx
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
    if user.id == ADMIN_CHAT_ID:
        return
    if ctx.user_data.get("step") != "awaiting_screenshot" or not ctx.user_data.get("plan_label"):
        await update.message.reply_text("אנא לחץ /start ובחר חבילה תחילה.")
        return
    file_id = update.message.photo[-1].file_id
    plan_str = ctx.user_data["plan_label"]
    db_save_pending(user.id, user.username or "", user.full_name, plan_str, file_id)
    ctx.user_data["step"] = "pending_approval"
    caption = (
        f"💳 *בקשת הצטרפות חדשה*\n\n"
        f"👤 {user.full_name}\n"
        f"📱 @{user.username or 'אין'}\n"
        f"🆔 `{user.id}`\n"
        f"📦 {plan_str}"
    )
    await ctx.bot.send_photo(
        chat_id=ADMIN_CHAT_ID, photo=file_id, caption=caption, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ אשר", callback_data=f"approve:{user.id}"),
            InlineKeyboardButton("❌ דחה",  callback_data=f"reject:{user.id}"),
        ]])
    )
    await update.message.reply_text("📨 *התקבל!*\n⏳ ממתין לאישור — נעדכן אותך בקרוב 🙏", parse_mode="Markdown")


# ── Admin approval buttons ────────────────────────────────────────────────────
async def cb_admin_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.answer("אין לך הרשאה!", show_alert=True); return
    await query.answer()
    action, uid_str = query.data.split(":")
    user_id = int(uid_str)
    row = db_get_pending(user_id)
    if not row:
        await query.edit_message_caption("הבקשה כבר טופלה."); return
    _, username, full_name, plan_str, _, _ = row
    if action == "approve":
        plans = get_plans()
        days = next((int(p.get("days", 30)) for p in plans if plan_label(p) == plan_str), 30)
        expires = db_save_member(user_id, username, full_name, plan_str, days)
        db_remove_pending(user_id)
        expire_str = datetime.fromisoformat(expires).strftime("%d/%m/%Y")
        try:
            invite = await ctx.bot.create_chat_invite_link(
                chat_id=VIP_GROUP_ID, member_limit=1,
                expire_date=datetime.now() + timedelta(hours=24), name=f"VIP-{user_id}")
            link_url = invite.invite_link
        except Exception as e:
            link_url = None; log.error(f"Invite error: {e}")
        msg = (f"🎉 *אושרת לקבוצת ה-VIP!*\n\n📦 {plan_str}\n📅 עד: {expire_str}\n\n"
               f"👇 קישור לקבוצה:\n{link_url}" if link_url else
               f"🎉 *אושרת!*\n📦 {plan_str}\n📅 עד: {expire_str}\n\n⚠️ האדמין ישלח קישור ידני בקרוב.")
        await ctx.bot.send_message(user_id, msg, parse_mode="Markdown")
        await query.edit_message_caption(f"✅ אושר — {full_name} | עד {expire_str}")
    elif action == "reject":
        db_remove_pending(user_id)
        await ctx.bot.send_message(user_id, "❌ הבקשה לא אושרה. שלח שוב אם מדובר בטעות.")
        await query.edit_message_caption(f"❌ נדחה — {full_name}")


# ── Admin commands ────────────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(update, ctx):
        if update.effective_user.id != ADMIN_CHAT_ID:
            return
        return await func(update, ctx)
    return wrapper


@admin_only
async def cmd_help(update, ctx):
    await update.message.reply_text(
        "📋 *פקודות אדמין:*\n\n"
        "/plans — הצגת החבילות\n"
        "/setlink <קישור> [מספר] — שינוי קישור תשלום\n"
        "/setwelcome <טקסט> — שינוי הודעת פתיחה\n"
        "/addplan <שם>|<מחיר>|<ימים>|<קישור> — הוספת חבילה\n"
        "/delplan <מספר> — מחיקת חבילה\n"
        "/members — חברים פעילים\n"
        "/pending — בקשות ממתינות\n"
        "/approve <id> — אישור ידני\n"
        "/reject <id> — דחייה ידנית\n"
        "/kick <id> — הסרת חבר\n",
        parse_mode="Markdown"
    )


@admin_only
async def cmd_plans(update, ctx):
    plans = get_plans()
    if not plans:
        await update.message.reply_text("אין חבילות. הוסף עם /addplan"); return
    lines = ["📦 *החבילות הנוכחיות:*\n"]
    for i, p in enumerate(plans, 1):
        lines.append(f"*{i}.* {plan_label(p)} | {p['days']} ימים\n🔗 {p.get('payment_link') or 'ללא קישור'}\n")
    lines.append("\n/setlink <קישור> <מספר> — שינוי קישור")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def cmd_setlink(update, ctx):
    args = ctx.args
    if not args:
        await update.message.reply_text("שימוש: /setlink <קישור>\nלדוגמה: /setlink https://paybox.co.il/abc"); return
    link = args[0]
    plan_num = int(args[1]) - 1 if len(args) > 1 and args[1].isdigit() else 0
    s = load_settings()
    if not s["plans"] or plan_num >= len(s["plans"]):
        await update.message.reply_text("❌ מספר חבילה לא תקין. /plans לרשימה"); return
    s["plans"][plan_num]["payment_link"] = link
    save_settings(s)
    await update.message.reply_text(f"✅ קישור עודכן!\n📦 {plan_label(s['plans'][plan_num])}\n🔗 {link}")


@admin_only
async def cmd_setwelcome(update, ctx):
    if not ctx.args:
        await update.message.reply_text("שימוש: /setwelcome <הטקסט החדש>"); return
    text = " ".join(ctx.args)
    s = load_settings()
    s["welcome_message"] = text
    save_settings(s)
    await update.message.reply_text(f"✅ הודעת הפתיחה עודכנה!\n\n{text}")


@admin_only
async def cmd_addplan(update, ctx):
    if not ctx.args:
        await update.message.reply_text("שימוש: /addplan <שם>|<מחיר>|<ימים>|<קישור>\nלדוגמה: /addplan גישה חודשית|20|30|https://paybox.co.il/abc"); return
    parts = " ".join(ctx.args).split("|")
    if len(parts) < 3:
        await update.message.reply_text("❌ פורמט שגוי. צריך: שם|מחיר|ימים|קישור"); return
    new_plan = {"name": parts[0].strip(), "price": parts[1].strip(), "days": int(parts[2].strip()), "payment_link": parts[3].strip() if len(parts) > 3 else ""}
    s = load_settings()
    s["plans"].append(new_plan)
    save_settings(s)
    await update.message.reply_text(f"✅ חבילה נוספה!\n📦 {plan_label(new_plan)} | {new_plan['days']} ימים\n🔗 {new_plan['payment_link'] or 'ללא קישור'}")


@admin_only
async def cmd_delplan(update, ctx):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("שימוש: /delplan <מספר>"); return
    idx = int(ctx.args[0]) - 1
    s = load_settings()
    if idx < 0 or idx >= len(s["plans"]):
        await update.message.reply_text("❌ מספר לא תקין. /plans לרשימה"); return
    removed = s["plans"].pop(idx)
    save_settings(s)
    await update.message.reply_text(f"🗑 החבילה *{plan_label(removed)}* נמחקה.", parse_mode="Markdown")


@admin_only
async def cmd_members(update, ctx):
    rows = db_get_members()
    if not rows:
        await update.message.reply_text("אין חברים פעילים כרגע."); return
    lines = [f"👥 *חברים פעילים ({len(rows)}):*\n"]
    for row in rows:
        user_id, username, full_name, plan, expires_at, _ = row
        days = max(0, (datetime.fromisoformat(expires_at) - datetime.now()).days)
        expire_str = datetime.fromisoformat(expires_at).strftime("%d/%m/%Y")
        icon = "🔴" if days < 7 else "🟢"
        lines.append(f"{icon} {full_name} (@{username or '-'}) | עד {expire_str} ({days} ימים)\n🆔 `{user_id}`\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def cmd_pending(update, ctx):
    rows = db_get_pending()
    if not rows:
        await update.message.reply_text("✅ אין בקשות ממתינות."); return
    lines = [f"⏳ *בקשות ממתינות ({len(rows)}):*\n"]
    for row in rows:
        user_id, username, full_name, plan, _, _ = row
        lines.append(f"👤 {full_name} (@{username or '-'}) | {plan}\n🆔 `{user_id}`\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def cmd_approve(update, ctx):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("שימוש: /approve <user_id>"); return
    user_id = int(ctx.args[0])
    row = db_get_pending(user_id)
    if not row:
        await update.message.reply_text("❌ לא נמצאה בקשה ממתינה."); return
    _, username, full_name, plan_str, _, _ = row
    plans = get_plans()
    days = next((int(p.get("days", 30)) for p in plans if plan_label(p) == plan_str), 30)
    expires = db_save_member(user_id, username, full_name, plan_str, days)
    db_remove_pending(user_id)
    expire_str = datetime.fromisoformat(expires).strftime("%d/%m/%Y")
    try:
        invite = await ctx.bot.create_chat_invite_link(chat_id=VIP_GROUP_ID, member_limit=1, expire_date=datetime.now() + timedelta(hours=24), name=f"VIP-{user_id}")
        await ctx.bot.send_message(user_id, f"🎉 *אושרת לקבוצת ה-VIP!*\n\n📦 {plan_str}\n📅 עד: {expire_str}\n\n👇 קישור:\n{invite.invite_link}", parse_mode="Markdown")
    except Exception as e:
        await ctx.bot.send_message(user_id, f"🎉 אושרת! עד {expire_str}. האדמין ישלח קישור בקרוב.")
        log.error(f"Invite error: {e}")
    await update.message.reply_text(f"✅ {full_name} אושר/ה! עד {expire_str}")


@admin_only
async def cmd_reject(update, ctx):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("שימוש: /reject <user_id>"); return
    user_id = int(ctx.args[0])
    row = db_get_pending(user_id)
    if not row:
        await update.message.reply_text("❌ לא נמצאה בקשה."); return
    _, _, full_name, _, _, _ = row
    db_remove_pending(user_id)
    await ctx.bot.send_message(user_id, "❌ הבקשה לא אושרה. שלח שוב אם מדובר בטעות.")
    await update.message.reply_text(f"❌ {full_name} נדחה/תה.")


@admin_only
async def cmd_kick(update, ctx):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("שימוש: /kick <user_id>"); return
    user_id = int(ctx.args[0])
    try:
        await ctx.bot.ban_chat_member(VIP_GROUP_ID, user_id)
        await ctx.bot.unban_chat_member(VIP_GROUP_ID, user_id)
        db_remove_member(user_id)
        await update.message.reply_text(f"✅ המשתמש `{user_id}` הוסר.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")


# ── Expiry checker ────────────────────────────────────────────────────────────
async def check_expirations(ctx: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().isoformat()
    con = sqlite3.connect(DB_FILE)
    expired = con.execute("SELECT user_id, full_name FROM members WHERE expires_at < ?", (now,)).fetchall()
    for (user_id, full_name) in expired:
        try:
            await ctx.bot.ban_chat_member(VIP_GROUP_ID, user_id)
            await ctx.bot.unban_chat_member(VIP_GROUP_ID, user_id)
            await ctx.bot.send_message(user_id, "⏰ *המנוי שלך פג תוקף.*\n\nכדי להמשיך, חדש את המנוי:\n/start", parse_mode="Markdown")
            await ctx.bot.send_message(ADMIN_CHAT_ID, f"ℹ️ המנוי של {full_name} (`{user_id}`) פג — הוסר.", parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Could not remove {user_id}: {e}")
        con.execute("DELETE FROM members WHERE user_id=?", (user_id,))
    con.commit(); con.close()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("plans",      cmd_plans))
    app.add_handler(CommandHandler("setlink",    cmd_setlink))
    app.add_handler(CommandHandler("setwelcome", cmd_setwelcome))
    app.add_handler(CommandHandler("addplan",    cmd_addplan))
    app.add_handler(CommandHandler("delplan",    cmd_delplan))
    app.add_handler(CommandHandler("members",    cmd_members))
    app.add_handler(CommandHandler("pending",    cmd_pending))
    app.add_handler(CommandHandler("approve",    cmd_approve))
    app.add_handler(CommandHandler("reject",     cmd_reject))
    app.add_handler(CommandHandler("kick",       cmd_kick))
    app.add_handler(CallbackQueryHandler(cb_plan_chosen,  pattern=r"^plan:"))
    app.add_handler(CallbackQueryHandler(cb_admin_action, pattern=r"^(approve|reject):"))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    app.job_queue.run_repeating(check_expirations, interval=3600, first=30)

    log.info("✅ VIP Bot is running!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

