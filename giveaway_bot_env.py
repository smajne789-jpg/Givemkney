import os
import random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Загружаем переменные окружения из .env
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

giveaways = {}
giveaway_counter = 1

# --- UI админки ---
def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Создать конкурс", callback_data="create")],
        [InlineKeyboardButton("📋 Мои конкурсы", callback_data="list")]
    ])

# --- Старт ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("🎛 Админ панель", reply_markup=admin_menu())
    else:
        await update.message.reply_text("Участвуй в конкурсах 🎉")

# --- Создание конкурса ---
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("✍️ Введи текст конкурса:")
    context.user_data["step"] = "text"

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    step = context.user_data.get("step")
    if step == "text":
        context.user_data["text"] = update.message.text
        context.user_data["step"] = "winners"
        await update.message.reply_text("👥 Сколько победителей?")
    elif step == "winners":
        context.user_data["winners"] = int(update.message.text)
        context.user_data["step"] = "channel_or_skip"
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, есть канал", callback_data="need_sub_yes"),
                InlineKeyboardButton("❌ Нет", callback_data="need_sub_no")
            ]
        ]
        await update.message.reply_text("📢 Добавить канал для подписки?",
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    elif step == "channel":
        context.user_data["channel"] = update.message.text
        context.user_data["step"] = None
        keyboard = [[InlineKeyboardButton("🚀 Опубликовать", callback_data="publish")]]
        await update.message.reply_text("Готово!", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Выбор подписки ---
async def need_sub_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["step"] = "channel"
    await update.callback_query.message.reply_text("📢 Отправь @канал для проверки подписки:")

async def need_sub_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["channel"] = None
    context.user_data["step"] = None
    keyboard = [[InlineKeyboardButton("🚀 Опубликовать", callback_data="publish")]]
    await update.callback_query.message.reply_text("Готово!", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Проверка подписки ---
async def check_subscription(user_id, bot, channel):
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- Публикация конкурса ---
async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global giveaway_counter
    text = context.user_data["text"]
    winners = context.user_data["winners"]
    channel = context.user_data.get("channel")
    gid = str(giveaway_counter)
    giveaway_counter += 1
    giveaways[gid] = {"text": text, "winners": winners, "participants": [], "ended": False, "channel": channel}
    keyboard = [[InlineKeyboardButton("🎉 Участвовать", callback_data=f"join_{gid}")]]
    post_text = f"🎁 РОЗЫГРЫШ\n\n{text}"
    if channel:
        post_text += f"\n\n📢 Подпишись: {channel}"
    message = await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=post_text, reply_markup=InlineKeyboardMarkup(keyboard))
    giveaways[gid]["message_id"] = message.message_id
    await update.callback_query.message.reply_text(f"✅ Конкурс создан (ID {gid})", reply_markup=admin_menu())

# --- Участие (одна кнопка) ---
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gid = query.data.split("_")[1]
    user = query.from_user
    data = giveaways[gid]
    if data["ended"]:
        await query.answer("Розыгрыш завершён ❌")
        return
    if data["channel"]:
        subscribed = await check_subscription(user.id, context.bot, data["channel"])
        if not subscribed:
            await query.answer(f"❌ Подпишись на {data['channel']}", show_alert=True)
            return
    if user.id not in data["participants"]:
        data["participants"].append(user.id)
        await query.answer("Ты участвуешь 🎉", show_alert=True)
    else:
        await query.answer("Ты уже участвуешь")

# --- Список конкурсов ---
async def list_giveaways(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not giveaways:
        await update.callback_query.message.reply_text("Нет конкурсов")
        return
    keyboard = []
    for gid, data in giveaways.items():
        status = "✅" if data["ended"] else "🟢"
        keyboard.append([InlineKeyboardButton(f"{status} Конкурс {gid} ({len(data['participants'])})", callback_data=f"view_{gid}")])
    await update.callback_query.message.reply_text("📋 Конкурсы:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Просмотр конкурса ---
async def view_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = update.callback_query.data.split("_")[1]
    data = giveaways[gid]
    text = f"🎁 Конкурс {gid}\n👥 Участников: {len(data['participants'])}\n🏆 Победителей: {data['winners']}\n📢 Подписка: {data['channel'] or 'Нет'}\nСтатус: {'Завершён' if data['ended'] else 'Активен'}"
    keyboard = []
    if not data["ended"]:
        keyboard.append([InlineKeyboardButton("🛑 Завершить", callback_data=f"end_{gid}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="list")])
    await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Завершение конкурса ---
async def end_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gid = query.data.split("_")[1]
    data = giveaways[gid]
    participants = data["participants"]
    if not participants:
        await query.answer("Нет участников 😢", show_alert=True)
        return
    winners = random.sample(participants, min(data["winners"], len(participants)))
    winner_tags = [f"[победитель](tg://user?id={uid})" for uid in winners]
    text = data["text"] + "\n\n🏆 Победители:\n" + "\n".join(winner_tags)
    await context.bot.edit_message_text(chat_id=CHANNEL_USERNAME, message_id=data["message_id"], text=text, parse_mode="Markdown")
    data["ended"] = True
    await query.answer("Завершено ✅")

# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(create, pattern="create"))
    app.add_handler(CallbackQueryHandler(publish, pattern="publish"))
    app.add_handler(CallbackQueryHandler(list_giveaways, pattern="list"))
    app.add_handler(CallbackQueryHandler(view_giveaway, pattern="view_"))
    app.add_handler(CallbackQueryHandler(join, pattern="join_"))
    app.add_handler(CallbackQueryHandler(end_giveaway, pattern="end_"))  # 👈 ВСТАВЬ СЮДА
    app.add_handler(CallbackQueryHandler(need_sub_yes, pattern="need_sub_yes"))
    app.add_handler(CallbackQueryHandler(need_sub_no, pattern="need_sub_no"))
    app.add_handler(MessageHandler(filters.TEXT, handle_admin))
    print("🚀 Giveaway Bot (одна кнопка) запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
