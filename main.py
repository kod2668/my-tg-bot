import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# 1. Render Port Check အတွက် Dummy Web Server ဖွင့်ပေးခြင်း
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Web server running on port {port}")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# 2. Telegram Bot & Groq Setup
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

# သင့်ရဲ့ Main Owner ID
OWNER_ID = 7094887417  

# Admin များနှင့် Ban ထားသော သူများ၏ ID များကို သိမ်းရန် List များ
admin_ids = [OWNER_ID]
banned_ids = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in banned_ids:
        await update.message.reply_text("တောင်းပန်ပါတယ်၊ သင့်ကို ဒီ Bot အသုံးပြုခွင့် ပိတ်ပင်ထား (Ban) ပါတယ်။")
        return

    if user.id == OWNER_ID:
        await update.message.reply_text("မင်္ဂလာပါ Boss! Bot ပိုင်ရှင် ဝင်ရောက်လာပါပြီ။ 👑\n\nအမိန့်ပေးရန် Command များ:\n/ban [user_id] - လူတစ်ယောက်ကို ပိတ်ရန်\n/unban [user_id] - ပိတ်ထားသည်ကို ပြန်ဖွင့်ရန်\n/addadmin [user_id] - Admin အဖြစ်သတ်မှတ်ရန်")
    else:
        await update.message.reply_text("မင်္ဂလာပါ။ AI Bot က စတင်အလုပ်လုပ်နေပါပြီ။ ဘာကူညီပေးရမလဲခင်ဗျာ။")

# 3. Admin သတ်မှတ်ရန် Command (`/addadmin 123456789`)
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("ဒီခလုတ်ကို Owner သို့မဟုတ် ခွင့်ပြုချက်ရသူများသာ သုံးလို့ရပါတယ်။")
        return
    try:
        target_id = int(context.args[0])
        if target_id not in admin_ids:
            admin_ids.append(target_id)
            await update.message.reply_text(f"အောင်မြင်ပါသည်။ User ID: {target_id} ကို Admin အဖြစ် သတ်မှတ်လိုက်ပါပြီ။")
    except:
        await.update.message.reply_text("မှားယွင်းနေပါသည်။ ဥပမာ - `/addadmin 123456789` ဟု ရေးပါ။")

# 4. လူတစ်ယောက်ကို Ban ရန် Command (`/ban 123456789`)
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("ခွင့်ပြုချက်မရှိပါ။")
        return
    try:
        target_id = int(context.args[0])
        if target_id == OWNER_ID:
            await update.message.reply_text("Owner ကို ဘယ်လိုမှ Ban လို့ မရပါဘူး။")
            return
        if target_id not in banned_ids:
            banned_ids.append(target_id)
            await update.message.reply_text(f"User ID: {target_id} ကို အောင်မြင်စွာ Ban လိုက်ပါပြီ။")
    except:
        await update.message.reply_text("ဥပမာ - `/ban 123456789` ဟု သုံးပါ။")

# 5. Ban ထားတာကို ပြန်ဖြုတ်ရန် Command (`/unban 123456789`)
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("ခွင့်ပြုချက်မရှိပါ။")
        return
    try:
        target_id = int(context.args[0])
        if target_id in banned_ids:
            banned_ids.remove(target_id)
            await update.message.reply_text(f"User ID: {target_id} ကို Ban ထားခြင်းမှ ပြန်လည် ဖယ်ရှားပေးလိုက်ပါပြီ။")
    except:
        await update.message.reply_text("ဥပမာ - `/unban 123456789` ဟု သုံးပါ။")

# 6. စာများလာပို့သည့်အခါ Owner ဆီသို့ တိုက်ရိုက် အကြောင်းကြားခြင်းနှင့် AI ဖြေကြားခြင်း
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text
    
    # Ban ထားသူဆိုလျှင် လုံးဝမဖြေပါ
    if user.id in banned_ids:
        return

    # Owner မဟုတ်ဘဲ တခြားသူလာပို့ရင် Owner (`OWNER_ID`) ဆီကို တိုက်ရိုက် မက်ဆေ့နဲ့ လှမ်းပို့ပေးမယ်
    if user.id != OWNER_ID:
        alert_msg = f"🔔 **New User Message!**\n👤 Name: {user.first_name}\n🆔 ID: `{user.id}`\n💬 Message: {user_text}"
        try:
            await context.bot.send_message(chat_id=OWNER_ID, text=alert_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to alert owner: {e}")

    is_owner = (user.id == OWNER_ID)
    
    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": user_text}]
        )
        reply_text = completion.choices[0].message.content
        
        if is_owner:
            reply_text = f"[Boss 👑]\n{reply_text}"
            
        await update.message.reply_text(reply_text)
    except Exception as e:
        print(f"Groq API Error Details: {e}")
        await update.message.reply_text(f"Error: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handler များ ချိတ်ဆက်ခြင်း
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is polling...")
    app.run_polling()
