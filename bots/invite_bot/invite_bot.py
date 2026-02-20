import logging
import os
import json
import re
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, ChatInviteLink, ChatMember
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    ChatJoinRequestHandler,
    filters,
)

# --- Setup Logging ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
sys.path.append(PROJECT_ROOT)

from database import SessionLocal, User, InviteProfile

LOG_FILE = os.path.join(BASE_DIR, 'invite_bot.log')
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Files ---
CONFIG_FILE = Path(BASE_DIR) / 'invite_bot_config.json'
USER_INTERACTIONS_LOG_FILE = Path(BASE_DIR) / 'user_interactions.log'

# --- Conversation States ---
FILLING_FORM, CONFIRM_RULES = range(2)

def load_config():
    default = {
        "is_enabled": False,
        "bot_token": "",
        "main_chat_id": "",
        "topic_id": "",
        "link_ttl_minutes": 15,
        "repost_profile_for_existing_members": True,
        "start_message": "Willkommen!",
        "rules_message": "Bitte bestätige die Regeln mit OK.",
        "blocked_message": "Du bist gebannt.",
        "privacy_policy": "",
        "form_fields": []
    }
    if not CONFIG_FILE.exists(): return default
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return default

def log_user_interaction(user_id: int, username: str, action: str, details: str = ""):
    try:
        with open(USER_INTERACTIONS_LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            user_info = f"@{username}" if username else f"ID:{user_id}"
            f.write(f"[{timestamp}] User: {user_info} | Aktion: {action} | Details: {details}\n")
    except: pass

async def get_or_create_user(user_id: int, username: str, full_name: str):
    def _sync():
        with SessionLocal() as session:
            db_user = session.query(User).filter(User.id == user_id).first()
            if not db_user:
                db_user = User(id=user_id, username=username, full_name=full_name)
                session.add(db_user)
            else:
                db_user.username = username
                db_user.full_name = full_name
            session.commit()
    await asyncio.get_running_loop().run_in_executor(None, _sync)

async def save_profile_db(user_id: int, answers: dict):
    def _sync():
        with SessionLocal() as session:
            profile = session.query(InviteProfile).filter(InviteProfile.user_id == user_id).first()
            if not profile:
                profile = InviteProfile(user_id=user_id, answers=answers)
                session.add(profile)
            else:
                profile.answers = answers
                profile.created_at = datetime.utcnow()
            session.commit()
    await asyncio.get_running_loop().run_in_executor(None, _sync)

async def get_profile_db(user_id: int):
    def _sync():
        with SessionLocal() as session:
            profile = session.query(InviteProfile).filter(InviteProfile.user_id == user_id).first()
            return profile.answers if profile else None
    return await asyncio.get_running_loop().run_in_executor(None, _sync)

def escape_md(text):
    if not text: return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", str(text))

def get_enabled_fields(config):
    return [f for f in config.get("form_fields", []) if f.get("enabled", True)]

async def ask_next_field(update: Update, context: ContextTypes.DEFAULT_TYPE, config: dict):
    fields = get_enabled_fields(config)
    current_idx = context.user_data.get("form_idx", 0)
    
    if current_idx >= len(fields):
        regeln = config.get("rules_message", "Bitte bestätige die Regeln mit OK.")
        await update.effective_message.reply_text(regeln)
        await update.effective_message.reply_text("Bitte antworte mit *OK*, um fortzufahren\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return CONFIRM_RULES

    field = fields[current_idx]
    label = field["label"]
    if not field.get("required"): 
        label += "\n\n_Diese Frage kannst du mit 'nein' überspringen._"
    
    await update.effective_message.reply_text(label)
    return FILLING_FORM

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    await update.message.reply_text(config.get("start_message", "Nutze /letsgo zum Starten."))

async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.full_name)
    
    context.user_data["form_idx"] = 0
    context.user_data["answers"] = {"telegram_id": user.id, "username": user.username, "first_name": user.first_name}
    return await ask_next_field(update, context, config)

async def handle_field_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    fields = get_enabled_fields(config)
    idx = context.user_data.get("form_idx", 0)
    if idx >= len(fields): return await ask_next_field(update, context, config)

    field = fields[idx]
    user_input = None
    
    if field["type"] == "photo":
        if update.message.photo: user_input = update.message.photo[-1].file_id
        elif not field.get("required") and update.message.text and update.message.text.lower() == "nein": user_input = None
        else:
            await update.message.reply_text("⚠️ Bitte sende ein Foto.")
            return FILLING_FORM
    elif field["type"] == "number":
        text = update.message.text.strip() if update.message.text else ""
        if text.isdigit(): user_input = text
        elif not field.get("required") and text.lower() == "nein": user_input = None
        else:
            await update.message.reply_text("⚠️ Bitte gib eine Zahl ein.")
            return FILLING_FORM
    else:
        text = update.message.text.strip() if update.message.text else ""
        if not field.get("required") and text.lower() == "nein": user_input = None
        else: user_input = text

    context.user_data["answers"][field["id"]] = user_input
    context.user_data["form_idx"] = idx + 1
    return await ask_next_field(update, context, config)

async def rules_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != "ok":
        await update.message.reply_text("Bitte antworte mit *OK*.")
        return CONFIRM_RULES
    
    user_id = update.effective_user.id
    profile = context.user_data["answers"]
    await save_profile_db(user_id, profile)
    
    config = load_config()
    try:
        link = await context.bot.create_chat_invite_link(
            chat_id=int(config["main_chat_id"]), 
            expire_date=datetime.utcnow() + timedelta(minutes=config.get("link_ttl_minutes", 15)), 
            creates_join_request=True
        )
        await update.message.reply_text(f"✅ Profil erstellt\\!\n\nBeitreten:\n{escape_md(link.invite_link)}", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Link Error: {e}")
        await update.message.reply_text("⚠️ Fehler beim Link-Erstellen.")
    return ConversationHandler.END

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    user_id, chat_id = req.from_user.id, req.chat.id
    config = load_config()
    
    if str(chat_id) != str(config.get("main_chat_id")): return

    try:
        await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
        profile = await get_profile_db(user_id)
        if profile:
            # Hier könnte man die Profile-Post Logik einfügen (identisch zu vorher)
            logger.info(f"Approved {user_id} and profile found.")
    except Exception as e:
        logger.error(f"Approval failed: {e}")

def main():
    config = load_config()
    if not config.get("bot_token"): sys.exit(1)
    app = ApplicationBuilder().token(config["bot_token"]).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("letsgo", start_form)],
        states={
            FILLING_FORM: [MessageHandler(filters.ALL & ~filters.COMMAND, handle_field_input)],
            CONFIRM_RULES: [MessageHandler(filters.TEXT & ~filters.COMMAND, rules_confirmed)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )
    
    app.add_handler(CommandHandler("start", welcome))
    app.add_handler(conv_handler)
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    logger.info("Invite Bot (SQL) gestartet...")
    app.run_polling()

if __name__ == "__main__":
    main()
