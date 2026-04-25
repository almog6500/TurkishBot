import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# הגדרות כלליות
TOKEN = '8538355821:AAE6u-r4BlTKrGzOQVSvE1rzgJQNbvUBIcU'
ADMIN_ID = 217420509  
GROUP_ID = -1003803654378  
BIT_LINK = 'קישור_לביט_שלך_כאן'
PAYBOX_LINK = 'קישור_לפייבוקס_שלך_כאן'

bot = telebot.TeleBot(TOKEN)

def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    btn_bit = InlineKeyboardButton("תשלום בביט", url=BIT_LINK)
    btn_paybox = InlineKeyboardButton("תשלום בפייבוקס", url=PAYBOX_LINK)
    btn_done = InlineKeyboardButton("שילמתי ויש לי צילום מסך", callback_data="paid")
    btn_help = InlineKeyboardButton("אני צריך עזרה", callback_data="help")
    markup.add(btn_bit, btn_paybox, btn_done, btn_help)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = "ברוכים הבאים! \nכדי להצטרף לקבוצת ה VIP, אנא בחרו את אמצעי התשלום הנוח לכם. לאחר מכן, לחצו על הכפתור המתאים ושלחו צילום מסך של ההעברה."
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data in ['paid', 'help'])
def handle_user_actions(call):
    if call.data == 'paid':
        bot.send_message(call.message.chat.id, "מעולה! אנא שלחו לכאן את צילום המסך של התשלום.")
    elif call.data == 'help':
        bot.send_message(call.message.chat.id, "כתבו כאן הודעה שתרצו להעביר למנהל ואני אדאג להעביר אותה באופן מיידי.")
        bot.register_next_step_handler(call.message, forward_help_to_admin)

def forward_help_to_admin(message):
    bot.send_message(ADMIN_ID, f"הודעת עזרה ממשתמש @{message.from_user.username}:\n\n{message.text}")
    bot.send_message(message.chat.id, "ההודעה שלך הועברה בהצלחה. נחזור אליך בהקדם.")

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
