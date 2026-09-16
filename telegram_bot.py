import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_ID = 7094887417  # Boss (Owner) သီးသန့် ID
DB_NAME = "xinon_users.db"

# ==================== DATABASE INITIALIZATION ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vips (
            device_id TEXT PRIMARY KEY,
            expiry_date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id: int) -> bool:
    # Owner ဖြစ်နေရင် သို့မဟုတ် Database ထဲက Admin စာရင်းထဲ ပါနေရင် True ပေးမည်
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def clean_expired_vips():
    """သက်တမ်းကုန်သွားသော VIP များကို Database မှ အလိုအလျောက် ဖယ်ရှားရန်"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM vips WHERE expiry_date < ?", (now_str,))
    conn.commit()
    conn.close()

# ==================== COMMAND HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clean_expired_vips()
    
    if user_id == OWNER_ID:
        # Boss (Owner) အတွက် Admin ရော VIP ရော အကုန်လုပ်လို့ရတာကို ပြမည့် Menu
        await update.message.reply_text(
            "👑 **မင်္ဂလာပါ Boss (Owner)**\n"
            "*(သင့်တွင် Admin နှင့် VIP အားလုံးကို စီမံခန့်ခွဲနိုင်သော အပြည့်အဝ လုပ်ပိုင်ခွင့်ရှိသည်)*\n\n"
            "🔹 **Admin စီမံရန် (Owner သီးသန့်):**\n"
            "`/addadmin [user_id]`\n"
            "`/removeadmin [user_id]` (သို့) `/deladmin`\n"
            "`/listadmins`\n\n"
            "⭐ **VIP စီမံရန် (Owner နှင့် Admin များ):**\n"
            "`/addvip [Device_ID] [ရက်]` *(ဥပမာ: /addvip xdev_123 30)*\n"
            "`/removevip [Device_ID]` (သို့) `/delvip`\n"
            "`/listvips` *(VIP စာရင်းနှင့် ကျန်ရက်များ ကြည့်ရန်)*",
            parse_mode="Markdown"
        )
    elif is_admin(user_id):
        # သာမန် Admin များအတွက် (VIP သက်သက်သာ စီမံနိုင်မည်)
        await update.message.reply_text(
            "🛡 **မင်္ဂလာပါ Admin**\n\n"
            "⭐ **VIP စီမံရန်:**\n"
            "`/addvip [Device_ID] [ရက်]` *(ဥပမာ: /addvip xdev_123 30)*\n"
            "`/removevip [Device_ID]` (သို့) `/delvip`\n"
            "`/listvips` *(VIP စာရင်းနှင့် ကျန်ရက်များ ကြည့်ရန်)*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⛔ ခွင့်ပြုချက်မရှိပါ။")

# --- ADMIN MANAGEMENT (Owner သီးသန့်) ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ Command သည် Owner (Boss) သီးသန့် ဖြစ်ပါသည်။")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/addadmin 123456789`", parse_mode="Markdown")
        return
    
    new_admin_id = int(context.args[0])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (new_admin_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"👑 Admin အသစ်အဖြစ် အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ: `{new_admin_id}`", parse_mode="Markdown")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ Command သည် Owner (Boss) သီးသန့် ဖြစ်ပါသည်။")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ ဥပမာ - `/removeadmin 123456789`", parse_mode="Markdown")
        return
    
    target_admin_id = int(context.args[0])
    if target_admin_id == OWNER_ID:
        await update.message.reply_text("⚠️ Boss ၏ ID ကို ဖယ်ရှား၍ မရပါ။")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE admin_id = ?", (target_admin_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ Admin စာရင်းမှ အောင်မြင်စွာ ဖယ်ရှားပြီးပါပြီ: `{target_admin_id}`", parse_mode="Markdown")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ဤ Command သည် Owner (Boss) သီးသန့် ဖြစ်ပါသည်။")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admins")
    admins = cursor.fetchall()
    conn.close()
    
    admin_list_str = "\n".join([f"• `{a[0]}`" for a in admins]) if admins else "Admin မရှိသေးပါ။"
    await update.message.reply_text(f"📋 **လက်ရှိ Admin စာရင်းများ:**\n{admin_list_str}", parse_mode="Markdown")

# --- VIP MANAGEMENT (Owner နှင့် Admin များ အားလုံးသုံးနိုင်သည်) ---
async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):  # Owner ဖြစ်ရင်ရော Admin ဖြစ်ရင်ပါ True ဖြစ်므로 နှစ်ဖက်လုံး သုံးလို့ရပါပြီ
        await update.message.reply_text("⛔ ဤ Command ကို အသုံးပြုရန် ခွင့်ပြုချက် မရှိပါ။")
        return
    
    if len(context.args) < 2 or not context.args[1].isdigit():
        await update.message.reply_text("⚠️ အသုံးပြုပုံမှားနေပါသည်။\nဥပမာ - `/addvip xdev_abc123 30` (30 ရက်အတွက်)", parse_mode="Markdown")
        return
    
    dev_id = context.args[0]
    days = int(context.args[1])
    
    expiry_date = datetime.now() + timedelta(days=days)
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vips (device_id, expiry_date) VALUES (?, ?)
        ON CONFLICT(device_id) DO UPDATE SET expiry_date = ?
    """, (dev_id, expiry_str, expiry_str))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ **VIP အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ!**\n\n"
        f"🔹 Device ID: `{dev_id}`\n"
        f"⏳ သက်တမ်း: **ရက်ပေါင်း {days} ရက်**\n"
        f"📅 ကုန်ဆုံးမည့်ရက်: `{expiry_str}`",
        parse_mode="Markdown"
    )

async def remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ဤ Command ကို အသုံးပြုရန် ခွင့်ပြုချက် မရှိပါ။")
        return
    if not context.args:
        await update.message.reply_text("⚠️ ဥပမာ - `/removevip xdev_abc123`", parse_mode="Markdown")
        return
    
    dev_id = context.args[0]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vips WHERE device_id = ?", (dev_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ VIP စာရင်းမှ အောင်မြင်စွာ ဖယ်ရှားပြီးပါပြီ: `{dev_id}`", parse_mode="Markdown")

async def list_vips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ ဤ Command ကို အသုံးပြုရန် ခွင့်ပြုချက် မရှိပါ။")
        return
    
    clean_expired_vips()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT device_id, expiry_date FROM vips")
    vips = cursor.fetchall()
    conn.close()
    
    if not vips:
        await update.message.reply_text("📋 လက်တလော Active ဖြစ်နေသော VIP User မရှိသေးပါ။")
        return
    
    msg = f"📋 **လက်ရှိ VIP User စာရင်းများ (စုစုပေါင်း: {len(vips)} ယောက်):**\n\n"
    for v in vips:
        msg += f"• `ID:` {v[0]}\n  `ကုန်ဆုံးမည့်ရက်:` {v[1]}\n\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

# ==================== RUN BOT ====================
def run_telegram_bot():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "8854987165:AAHqjcgVAUoSEgtoIHabxAkPvZ-eoje5hcY":
        print("⚠️ Telegram Token မထည့်ထားပါ။")
        return

    
    try:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("addadmin", add_admin))
        application.add_handler(CommandHandler("removeadmin", remove_admin))
        application.add_handler(CommandHandler("deladmin", remove_admin))
        application.add_handler(CommandHandler("listadmins", list_admins))
        
        application.add_handler(CommandHandler("addvip", add_vip))
        application.add_handler(CommandHandler("removevip", remove_vip))
        application.add_handler(CommandHandler("delvip", remove_vip))
        application.add_handler(CommandHandler("listvips", list_vips))
        
        print("🤖 Management Telegram Bot ကို အောင်မြင်စွာ စတင်လည်ပတ်နေပါပြီ...")
        application.run_polling()
    except Exception as e:
        print(f"❌ Telegram Bot Error: {e}")
  
