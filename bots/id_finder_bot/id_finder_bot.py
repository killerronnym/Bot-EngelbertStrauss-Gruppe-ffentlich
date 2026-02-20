import logging
import os
import json
import sys
import asyncio
from datetime import datetime
from typing import Dict, Any, List

# --- Paths ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BOT_DIR))
sys.path.append(PROJECT_ROOT)

from database import SessionLocal, User, Activity, Topic, Broadcast, ModerationLog

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(BOT_DIR, "id_finder_config.json")

# --- Logging ---
LOG_FILE = os.path.join(BOT_DIR, "id_finder_bot.log")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    from telegram import Update, ForumTopic
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
except ImportError:
    logger.error("Erforderliche Bibliothek 'python-telegram-bot' nicht gefunden!")
    sys.exit(1)

# --- Globals & Locks ---
CONFIG_CACHE = {}

# --- Config Management ---
def validate_config(cfg: Dict[str, Any]) -> bool:
    required_keys = {
        "bot_token": str,
        "main_group_id": int,
        "message_logging_enabled": bool
    }
    
    id_fields = ["main_group_id", "admin_group_id", "admin_log_topic_id"]
    for field in id_fields:
        if field in cfg and isinstance(cfg[field], str):
            try:
                cfg[field] = int(cfg[field])
                logger.info(f"Feld '{field}' von String zu Int konvertiert.")
            except ValueError:
                pass

    for key, key_type in required_keys.items():
        if key not in cfg:
            logger.critical(f"FEHLER: Fehlender Schlüssel in der Konfiguration: '{key}'")
            return False
        if not isinstance(cfg[key], key_type):
            logger.critical(f"FEHLER: Falscher Datentyp für '{key}'. Erwartet: {key_type.__name__}, gefunden: {type(cfg[key]).__name__}")
            return False
    return True

# --- Database Sync Helpers ---
async def update_user_db(user_id: int, username: str, full_name: str):
    def _sync():
        with SessionLocal() as session:
            db_user = session.query(User).filter(User.id == user_id).first()
            if not db_user:
                db_user = User(id=user_id, username=username, full_name=full_name)
                session.add(db_user)
            else:
                db_user.username = username
                db_user.full_name = full_name
                db_user.last_seen = datetime.utcnow()
            session.commit()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _sync)

async def log_activity_db(entry: Dict[str, Any]):
    def _sync():
        with SessionLocal() as session:
            activity = Activity(
                ts=datetime.fromisoformat(entry["ts"]),
                chat_id=entry["chat_id"],
                chat_type=entry["chat_type"],
                chat_title=entry["chat_title"],
                thread_id=entry["thread_id"],
                message_id=entry["message_id"],
                user_id=entry["user_id"],
                text=entry["text"],
                msg_type=entry["msg_type"],
                has_media=entry["has_media"],
                media_kind=entry["media_kind"],
                file_id=entry["file_id"],
                is_command=entry["is_command"]
            )
            session.add(activity)
            session.commit()
            
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _sync)

async def update_topic_db(chat_id: int, topic_id: int, name: str):
    def _sync():
        with SessionLocal() as session:
            topic = session.query(Topic).filter(Topic.chat_id == chat_id, Topic.topic_id == topic_id).first()
            if not topic:
                topic = Topic(chat_id=chat_id, topic_id=topic_id, name=name)
                session.add(topic)
            else:
                topic.name = name
            session.commit()
            
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _sync)

# --- Topic Registry ---
async def update_topic_registry(chat_id: int, chat_title: str, topic_id: int, topic_name: str):
    await update_topic_db(chat_id, topic_id, topic_name)
    logger.info(f"Topic '{topic_name}' ({topic_id}) in Gruppe '{chat_title}' ({chat_id}) registriert/aktualisiert.")

async def handle_topic_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.forum_topic_created:
        topic: ForumTopic = update.message.forum_topic_created
        chat = update.effective_chat
        await update_topic_registry(chat.id, chat.title, topic.message_thread_id, topic.name)

# --- Broadcast Engine ---
async def update_broadcast_status(broadcast_id: str, new_status: str, sent_at: str = None, error_msg: str = None):
    def _sync():
        with SessionLocal() as session:
            b = session.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
            if b:
                b.status = new_status
                if sent_at: b.sent_at = datetime.fromisoformat(sent_at)
                if error_msg: b.error_msg = error_msg
                session.commit()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _sync)

async def send_scheduled_broadcast(context: ContextTypes.DEFAULT_TYPE, broadcast_id: str):
    logger.info(f"Sende geplanten Broadcast {broadcast_id}...")
    
    def _get_b():
        with SessionLocal() as session:
            return session.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
    
    loop = asyncio.get_running_loop()
    broadcast_item = await loop.run_in_executor(None, _get_b)

    if not broadcast_item or broadcast_item.status == "sent":
        return

    main_group = CONFIG_CACHE.get("main_group_id")
    if not main_group:
        await update_broadcast_status(broadcast_id, "error", error_msg="Main group ID not configured.")
        return

    try:
        await context.bot.send_message(
            chat_id=main_group,
            text=broadcast_item.text,
            message_thread_id=broadcast_item.topic_id,
            disable_notification=broadcast_item.silent_send
        )
        await update_broadcast_status(broadcast_id, "sent", sent_at=datetime.utcnow().isoformat())
        logger.info(f"Broadcast {broadcast_id} erfolgreich gesendet.")
    except Exception as e:
        logger.error(f"Fehler beim Senden von Broadcast {broadcast_id}: {e}")
        await update_broadcast_status(broadcast_id, "error", error_msg=str(e))

# --- Activity Tracking ---
async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not all([msg, user, chat]): return
    if not CONFIG_CACHE.get("message_logging_enabled", True): return

    # --- Topic/Group Auto-Discovery ---
    if chat.type in ["group", "supergroup"]:
        chat_title = chat.title or str(chat.id)
        topic_name = "General"
        topic_id = chat.id

        if chat.is_forum and msg.message_thread_id:
            topic_id = msg.message_thread_id
            try:
                forum_topic = await context.bot.get_forum_topic(chat_id=chat.id, message_thread_id=topic_id)
                topic_name = forum_topic.name
            except Exception:
                topic_name = f"Topic-{topic_id}"
        
        await update_topic_registry(chat.id, chat_title, topic_id, topic_name)

    # --- SQL User Update ---
    await update_user_db(user.id, user.username, user.full_name)

    # --- SQL Activity Log ---
    has_media = bool(msg.photo or msg.video or msg.document or msg.sticker or msg.voice or msg.audio or msg.animation)
    media_kind, file_id = None, None
    if msg.photo: media_kind, file_id = "photo", msg.photo[-1].file_id
    elif msg.video: media_kind, file_id = "video", msg.video.file_id
    elif msg.document: media_kind, file_id = "document", msg.document.file_id
    elif msg.sticker: media_kind, file_id = "sticker", msg.sticker.file_id
    elif msg.voice: media_kind, file_id = "voice", msg.voice.file_id
    elif msg.audio: media_kind, file_id = "audio", msg.audio.file_id
    elif msg.animation: media_kind, file_id = "animation", msg.animation.file_id

    log_entry = {
        "ts": datetime.now().isoformat(),
        "chat_id": chat.id,
        "chat_type": chat.type,
        "chat_title": chat.title,
        "thread_id": msg.message_thread_id,
        "message_id": msg.message_id,
        "user_id": user.id,
        "text": msg.text or msg.caption or "",
        "msg_type": "text" if msg.text else (media_kind or "unknown"),
        "has_media": has_media,
        "media_kind": media_kind,
        "file_id": file_id,
        "is_command": msg.text.startswith("/") if msg.text else False
    }

    await log_activity_db(log_entry)

# --- Commands ---
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👤 *Benutzer-ID:* `{update.effective_user.id}`\n"
        f"💬 *Chat-ID:* `{update.effective_chat.id}`\n"
        f"🏷️ *Topic-ID:* `{update.effective_message.message_thread_id or 'Kein Topic'}`",
        parse_mode="Markdown"
    )

def main():
    if not os.path.exists(CONFIG_FILE):
        logger.critical("Konfigurationsdatei fehlt!")
        sys.exit(1)
        
    with open(CONFIG_FILE, "r") as f:
        try: config = json.load(f)
        except: sys.exit(1)
    
    if not validate_config(config): sys.exit(1)
        
    global CONFIG_CACHE
    CONFIG_CACHE = config

    app = ApplicationBuilder().token(config["bot_token"]).build()
    
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_activity))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(MessageHandler(filters.StatusUpdate.FORUM_TOPIC_CREATED, handle_topic_creation))

    logger.info("ID-Finder Bot startet (SQL Mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
