import os
import json
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys
import time
import requests
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, flash, redirect, url_for, jsonify, send_file, abort, session
)
from sqlalchemy import func, desc, extract, and_
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import uuid
import threading
import tempfile

# ✅ Umfassender Pfad-Fix für NAS/Docker Umgebungen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
if PROJECT_ROOT not in sys.path: sys.path.append(PROJECT_ROOT)

from database import SessionLocal, User, Activity, Topic, Broadcast, ModerationLog, init_db
from updater import Updater

# --- App Setup ---
app = Flask(__name__, template_folder="src")
app.secret_key = "b13f172933b9a1274adb024d47fc7552d2e85864693cb9a2"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", handlers=[RotatingFileHandler("app.log", maxBytes=10240, backupCount=5), logging.StreamHandler(sys.stdout)], force=True)
log = logging.getLogger(__name__)

CRITICAL_ERRORS_LOG_FILE = os.path.join(BASE_DIR, "critical_errors.log")

# --- Pfade ---
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BOTS_DIR = os.path.join(PROJECT_ROOT, "bots")
VERSION_FILE = os.path.join(PROJECT_ROOT, "version.json")
DASHBOARD_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")

# Config Files (Bots)
QUIZ_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot_config.json")
UMFRAGE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot_config.json")
INVITE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "invite_bot", "invite_bot_config.json")
INVITE_BOT_LOG_FILE = os.path.join(BOTS_DIR, "invite_bot", "invite_bot.log")
INVITE_BOT_INTERACTION_LOG = os.path.join(BOTS_DIR, "invite_bot", "user_interactions.log")
OUTFIT_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_config.json")
OUTFIT_BOT_DATA_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_data.json")
OUTFIT_BOT_LOG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")
ID_FINDER_CONFIG_FILE = os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_config.json")
MINECRAFT_STATUS_CONFIG_FILE = os.path.join(DATA_DIR, "minecraft_status_config.json")
MINECRAFT_STATUS_CACHE_FILE = os.path.join(DATA_DIR, "minecraft_status_cache.json")

VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
if not os.path.exists(VENV_PYTHON): VENV_PYTHON = sys.executable

MATCH_CONFIG = {
    "quiz": {"pattern": "quiz_bot.py", "script": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.py"), "log": os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot.log")},
    "umfrage": {"pattern": "umfrage_bot.py", "script": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.py"), "log": os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot.log")},
    "outfit": {"pattern": "outfit_bot.py", "script": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.py"), "log": os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")},
    "invite": {"pattern": "invite_bot.py", "script": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.py"), "log": os.path.join(BOTS_DIR, "invite_bot", "invite_bot.log")},
    "id_finder": {"pattern": "id_finder_bot.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_bot.log")},
    "minecraft": {"pattern": "minecraft_bridge.py", "script": os.path.join(BOTS_DIR, "id_finder_bot", "minecraft_bridge.py"), "log": os.path.join(BOTS_DIR, "id_finder_bot", "minecraft_bridge.log")},
}

# --- Database Init ---
with app.app_context():
    init_db()

# --- Helpers ---
JSON_FILE_LOCK = threading.Lock()

def load_json(path, default=None):
    fallback = default if default is not None else {}
    if not os.path.exists(path):
        return fallback
    try:
        with JSON_FILE_LOCK:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Could not load JSON from {path}: {e}")
        return fallback

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        with JSON_FILE_LOCK:
            os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def to_int(val, default=None):
    if val is None or val == "" or str(val).lower() == "null": return default
    try: return int(val)
    except (TypeError, ValueError): return default

def get_bot_status():
    try:
        output = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True, check=False).stdout
        return {k: {"running": cfg["pattern"] in output} for k, cfg in MATCH_CONFIG.items()}
    except: return {k: {"running": False} for k in MATCH_CONFIG}

_updater_instance = None
def get_updater():
    global _updater_instance
    if _updater_instance: return _updater_instance
    cfg = load_json(DASHBOARD_CONFIG_FILE)
    if not cfg or "github_owner" not in cfg: return None
    _updater_instance = Updater(
        repo_owner=cfg["github_owner"],
        repo_name=cfg["github_repo"],
        current_version_file=VERSION_FILE,
        project_root=PROJECT_ROOT
    )
    return _updater_instance

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%H:%M:%S | %d.%m.%Y'):
    if value is None: return ""
    try:
        if isinstance(value, datetime): dt = value
        elif isinstance(value, (int, float)): dt = datetime.fromtimestamp(value)
        else: dt = datetime.fromisoformat(str(value))
        return dt.strftime(format)
    except: return str(value)

@app.context_processor
def inject_globals():
    return {"bot_status": get_bot_status()}

# --- AUTH ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            session["user"] = "Gast-Admin"
            session["role"] = "admin"
        return f(*args, **kwargs)
    return decorated_function

# --- SETUP CHECK ---
def is_setup_done():
    return os.path.exists(USERS_FILE) and os.path.exists(DASHBOARD_CONFIG_FILE)

@app.before_request
def check_for_setup():
    if request.path.startswith('/static') or request.path == '/setup': return
    if not is_setup_done(): return redirect(url_for('setup_wizard'))

@app.route("/setup", methods=["GET", "POST"])
def setup_wizard():
    if is_setup_done(): return redirect(url_for('index'))
    if request.method == "POST":
        admin_user, admin_pass, repo_path = request.form.get("admin_user"), request.form.get("admin_pass"), request.form.get("repo_path")
        bot_token = request.form.get("bot_token")
        save_json(USERS_FILE, {admin_user: {"password": generate_password_hash(admin_pass), "role": "admin"}})
        owner, repo = repo_path.split("/") if "/" in repo_path else ("killerronnym", "Bot-EngelbertStrauss-Gruppe-ffentlich")
        save_json(DASHBOARD_CONFIG_FILE, {"github_owner": owner, "github_repo": repo, "secret_key": str(uuid.uuid4()), "quiz": {"token": bot_token, "channel_id": "", "topic_id": ""}, "umfrage": {"token": bot_token, "channel_id": "", "topic_id": ""}})
        if not os.path.exists(VERSION_FILE): save_json(VERSION_FILE, {"version": "1.0.0", "release_date": datetime.now().isoformat()})
        flash("Setup abgeschlossen!", "success")
        return redirect(url_for("login"))
    return render_template("setup.html")

@app.route("/login")
def login():
    session["user"] = "Gast-Admin"
    session["role"] = "admin"
    return redirect(url_for("index"))

# --- MAIN DASHBOARD ---
@app.route("/")
@login_required
def index(): return render_template("index.html", version=load_json(VERSION_FILE, {"version": "1.0.0"}))

@app.route("/live_moderation")
@login_required
def live_moderation_legacy_redirect():
    query_args = request.args.to_dict(flat=True)
    return redirect(url_for("live_moderation", **query_args), code=301)


def _parse_filter_int(value, field_name):
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        flash(f"Ungültiger {field_name}-Filter wurde ignoriert.", "warning")
        return None


@app.route("/live-moderation")
@login_required
def live_moderation():
    raw_chat_id = request.args.get("chat_id")
    raw_topic_id = request.args.get("topic_id")

    chat_id = _parse_filter_int(raw_chat_id, "chat_id")
    topic_id = "all" if raw_topic_id == "all" else _parse_filter_int(raw_topic_id, "topic_id")

    with SessionLocal() as db:
        query = db.query(Activity)
        if chat_id is not None:
            query = query.filter(Activity.chat_id == chat_id)
        if topic_id not in (None, "all"):
            query = query.filter(Activity.thread_id == topic_id)
        messages = query.options(joinedload(Activity.user)).order_by(Activity.ts.desc()).limit(100).all()
        topics_db = db.query(Topic).order_by(Topic.chat_id.asc(), Topic.topic_id.asc()).all()

        # Fetch Chat Titles
        unique_chat_ids = list(set(t.chat_id for t in topics_db))
        chat_titles = {}
        if unique_chat_ids:
            try:
                # Group by chat_id to get one title per chat. 
                # This assumes title doesn't change much or getting any title is fine.
                chat_titles_rows = db.query(Activity.chat_id, Activity.chat_title)\
                    .filter(Activity.chat_id.in_(unique_chat_ids))\
                    .filter(Activity.chat_title.isnot(None))\
                    .group_by(Activity.chat_id).all()
                chat_titles = {r[0]: r[1] for r in chat_titles_rows}
            except Exception as e:
                log.error(f"Error fetching chat titles: {e}")

    topic_dict = {}
    for t in topics_db:
        cid = str(t.chat_id)
        if cid not in topic_dict:
            display_name = chat_titles.get(t.chat_id, f"Chat {cid}")
            topic_dict[cid] = {"name": display_name, "topics": {}}
        topic_dict[cid]["topics"][str(t.topic_id)] = t.name
    return render_template("live_moderation.html", messages=messages, topics=topic_dict, mod_config=load_json(os.path.join(DATA_DIR, "moderation_config.json"), {}), selected_chat_id=str(chat_id) if chat_id is not None else None, selected_topic_id=str(topic_id) if topic_id is not None else None)

@app.route("/live-moderation/config", methods=["POST"])
@login_required
def live_moderation_config():
    config = {"max_warnings": int(request.form.get("max_warnings", 3)), "warning_text": request.form.get("warning_text", ""), "public_delete_notice_text": request.form.get("public_delete_notice_text", ""), "public_delete_notice_duration": int(request.form.get("public_delete_notice_duration", 60))}
    save_json(os.path.join(DATA_DIR, "moderation_config.json"), config)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("live_moderation"))

@app.route("/live-moderation/delete", methods=["POST"])
@login_required
def live_moderation_delete():
    user_id = request.form.get("user_id")
    chat_id = request.form.get("chat_id")
    message_id = request.form.get("message_id")
    topic_id = request.form.get("topic_id")
    action = request.form.get("action") # delete, warn
    if action not in {"delete", "warn"}:
        flash("Ungültige Moderationsaktion: Aktion wurde abgebrochen.", "danger")
        return redirect(url_for("live_moderation"))

    reason = request.form.get("reason_preset")
    if reason == "other":
        reason = request.form.get("reason_custom")


    chat_id_int = _parse_filter_int(chat_id, "chat_id")
    message_id_int = _parse_filter_int(message_id, "message_id")
    user_id_int = _parse_filter_int(user_id, "user_id")
    topic_id_int = _parse_filter_int(topic_id, "topic_id") if topic_id not in (None, "", "None", "all") else None

    if chat_id_int is None or message_id_int is None or user_id_int is None:
        flash("Ungültige Moderationsdaten: Aktion wurde abgebrochen.", "danger")
        return redirect(url_for("live_moderation"))
    
    post_to_topic = "post_to_topic" in request.form
    send_dm = "send_dm" in request.form
    
    user_name = request.form.get("user_name") # For template rendering
    
    # Get Token
    token = load_json(ID_FINDER_CONFIG_FILE).get("bot_token")
    if not token:
        flash("Fehler: Bot-Token nicht konfiguriert (ID-Finder).", "danger")
        return redirect(url_for("live_moderation"))
        
    mod_cfg = load_json(os.path.join(DATA_DIR, "moderation_config.json"), {})

    # 1. Delete Message
    try:
        del_res = requests.post(f"https://api.telegram.org/bot{token}/deleteMessage", json={"chat_id": chat_id_int, "message_id": message_id_int})
        if del_res.status_code != 200:
             log.error(f"Failed to delete message: {del_res.text}")
             flash(f"Fehler beim Löschen der Nachricht: {del_res.text}", "danger")
        else:
            # Update DB to mark as deleted
            with SessionLocal() as db:
                msg = db.query(Activity).filter(Activity.message_id == message_id_int, Activity.chat_id == chat_id_int).first()
                if msg:
                    msg.is_deleted = True
                    db.commit()

    except Exception as e:
        log.error(f"Error deleting message: {e}")
        flash(f"Fehler beim Löschen der Nachricht: {e}", "danger")

    # 2. Log / Warn
    with SessionLocal() as db:
        # Create Mod Log
        mod_log = ModerationLog(
            chat_id=chat_id_int,
            user_id=user_id_int,
            admin_id=0, # Web Admin
            action=action,
            reason=reason,
            message_id=message_id_int
        )
        db.add(mod_log)
        
        db.commit() # Commit to get ID and save log

        # Determine Warn Count (for placeholders)
        warn_count = db.query(ModerationLog).filter(ModerationLog.user_id == user_id_int, ModerationLog.action == "warn").count()

        # Send DM?
        if send_dm:
             warn_text = mod_cfg.get("warning_text", "")
             if warn_text:
                 txt = warn_text.replace("{user}", user_name or str(user_id_int))\
                                .replace("{reason}", reason or "Verstoß")\
                                .replace("{warn_count}", str(warn_count))\
                                .replace("{max_warnings}", str(mod_cfg.get("max_warnings", 3)))\
                                .replace("{group}", request.form.get("chat_name") or "der Gruppe")
                 
                 try:
                     dm_res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": user_id_int, "text": txt})
                     if dm_res.status_code != 200:
                         log.error(f"Failed to send DM: {dm_res.text}")
                         # Maybe user blocked bot or hasn't started it
                 except Exception as e: log.error(f"Failed to send DM: {e}")

        # Post to Topic?
        if post_to_topic:
             notice_text = mod_cfg.get("public_delete_notice_text", "")
             if notice_text:
                 txt = notice_text.replace("{user}", user_name or str(user_id_int)).replace("{reason}", reason or "Verstoß")
                 payload = {"chat_id": chat_id_int, "text": txt}
                 
                 # IMPORTANT: thread_id handling. 
                 # If topic_id is "None" or 0 or empty, we shouldn't send message_thread_id unless it's a supergroup with topics enabled.
                 # If the message came from a topic, we reply to that topic.
                 if topic_id_int and topic_id_int != 0:
                     payload["message_thread_id"] = topic_id_int
                 
                 try:
                     res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
                     
                     if res.status_code != 200:
                         log.error(f"Failed to post topic notice: {res.text}")
                     else:
                         # Auto-delete notice?
                         duration = mod_cfg.get("public_delete_notice_duration", 60)
                         if duration > 0:
                             sent_msg_id = res.json().get("result", {}).get("message_id")
                             if sent_msg_id:
                                 def delete_later(chat, msg, delay):
                                     time.sleep(delay)
                                     try:
                                         requests.post(f"https://api.telegram.org/bot{token}/deleteMessage", json={"chat_id": chat, "message_id": msg})
                                     except Exception as e:
                                         log.error(f"Error auto-deleting notice: {e}")
                                 
                                 threading.Thread(target=delete_later, args=(chat_id_int, sent_msg_id, duration), daemon=True).start()
                 except Exception as e: log.error(f"Failed to post topic notice: {e}")

    flash(f"Aktion '{action}' ausgeführt.", "success")
    topic_redirect = "all" if topic_id == "all" else topic_id_int
    return redirect(url_for("live_moderation", chat_id=chat_id_int, topic_id=topic_redirect))

# --- ID FINDER ---
@app.route("/id-finder")
@login_required
def id_finder_dashboard():
    with SessionLocal() as db:
        users = db.query(User).all()
    return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE), is_running=get_bot_status()["id_finder"]["running"], user_registry=users)

@app.route("/id-finder/save-config", methods=["POST"])
@login_required
def id_finder_save_config():
    cfg = load_json(ID_FINDER_CONFIG_FILE)
    cfg.update({"bot_token": request.form.get("bot_token"), "admin_group_id": to_int(request.form.get("admin_group_id")), "main_group_id": to_int(request.form.get("main_group_id")), "admin_log_topic_id": to_int(request.form.get("admin_log_topic_id")), "delete_commands": "delete_commands" in request.form, "bot_message_cleanup_seconds": max(0, to_int(request.form.get("bot_message_cleanup_seconds"), 0)), "message_logging_enabled": "message_logging_enabled" in request.form, "message_logging_ignore_commands": "message_logging_ignore_commands" in request.form, "message_logging_groups_only": "message_logging_groups_only" in request.form})
    save_json(ID_FINDER_CONFIG_FILE, cfg)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/analytics")
@login_required
def id_finder_analytics(): 
    days = request.args.get("days", type=int)
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    with SessionLocal() as db:
        total_users = db.query(User).count()
        total_messages = db.query(Activity).count()
        
        # Build query with filters
        query = db.query(Activity)
        if days:
            start_date = datetime.utcnow() - timedelta(days=days)
            query = query.filter(Activity.ts >= start_date)
        if month and month > 0:
            query = query.filter(extract('month', Activity.ts) == month)
        if year and year > 0:
            query = query.filter(extract('year', Activity.ts) == year)

        # Leaderboard
        leaderboard = db.query(
            User.id, 
            User.full_name, 
            User.username, 
            func.count(Activity.id).label('count'),
            func.sum(Activity.has_media).label('media_count')
        ).join(Activity, Activity.user_id == User.id)\
        .filter(Activity.id.in_(query.with_entities(Activity.id)))\
        .group_by(User.id).order_by(desc('count')).limit(10).all()

        # Timeline
        timeline_raw = db.query(func.date(Activity.ts).label('date'), func.count(Activity.id).label('count'))\
            .filter(Activity.id.in_(query.with_entities(Activity.id)))\
            .group_by('date').order_by('date').all()
            
        timeline = {"labels": [r.date for r in timeline_raw], "total": [r.count for r in timeline_raw]}
        
        # Hours
        hours_raw = db.query(func.strftime('%H', Activity.ts).label('hour'), func.count(Activity.id).label('count'))\
            .filter(Activity.id.in_(query.with_entities(Activity.id)))\
            .group_by('hour').all()
        busiest_hours = [0] * 24
        for r in hours_raw: busiest_hours[int(r.hour)] = r.count

        # Days
        # SQLite uses 0=Sunday, 6=Saturday for strftime('%w', ...) 
        # Chart.js often expects 0=Monday if labels are Mo,Di... but we can map it.
        # Let's map SQLite 0..6 (Sun..Sat) to 0..6 (Mon..Sun) for the chart labels provided in HTML ['Mo', 'Di', ...]
        days_raw = db.query(func.strftime('%w', Activity.ts).label('dow'), func.count(Activity.id).label('count'))\
            .filter(Activity.id.in_(query.with_entities(Activity.id)))\
            .group_by('dow').all()
        
        # Map: Sun(0)->6, Mon(1)->0, Tue(2)->1, ... Sat(6)->5
        busiest_days = [0] * 7
        for r in days_raw:
            dow_sqlite = int(r.dow)
            dow_chart = (dow_sqlite - 1) % 7
            busiest_days[dow_chart] = r.count

    return render_template("id_finder_analytics.html", 
        stats={"total_users": total_users, "total_messages": total_messages}, 
        activity={
            "leaderboard": [{
                "uid": r[0], 
                "name": r[1] or r[2] or f"User {r[0]}", 
                "msgs": r[3], 
                "media": r[4] or 0, 
                "reacts": 0 
            } for r in leaderboard], 
            "timeline": timeline, 
            "busiest_hours": busiest_hours, 
            "busiest_days": busiest_days
        }
    )

@app.route("/api/id-finder/user-activity/<user_id>")
@login_required
def api_user_activity(user_id):
    days = request.args.get("days", type=int)
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    user_id_int = to_int(user_id)
    if user_id_int is None:
        return jsonify({"error": "invalid user_id"}), 400

    with SessionLocal() as db:
        query = db.query(func.date(Activity.ts).label('date'), func.count(Activity.id).label('count'))\
            .filter(Activity.user_id == user_id_int)
        
        if days:
            start_date = datetime.utcnow() - timedelta(days=days)
            query = query.filter(Activity.ts >= start_date)
        if month and month > 0:
            query = query.filter(extract('month', Activity.ts) == month)
        if year and year > 0:
            query = query.filter(extract('year', Activity.ts) == year)
            
        raw = query.group_by('date').order_by('date').all()
        
        # We need to match the global labels. 
        # Ideally, we return a dict {date: count} and let frontend map it, 
        # or we return an array matching the global labels if passed.
        # For simplicity, let's return objects {t: date, y: count} which Chart.js handles well with time scales,
        # but here we used category scale (strings). 
        
        # Let's return a map.
        data_map = {r.date: r.count for r in raw}
        
        # Get global labels from query (re-run logic or pass from frontend? Frontend is easier but insecure/messy)
        # Better: Re-generate global labels for the same period to ensure alignment, 
        # OR just return the sparse data and let frontend align it with the existing labels.
        
        # We will assume the frontend has the labels from the page load.
        # To align perfectly, we need those labels. 
        # But we can just return the map and let JS fill the array.
        return jsonify({"timeline_map": data_map})

@app.route("/id-finder/commands")
@login_required
def id_finder_commands(): return render_template("id_finder_commands.html")

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel(): return render_template("id_finder_admin_panel.html", admins=load_json(ADMINS_FILE, {}), available_permissions={"can_warn": "Nutzer verwarnen", "can_delete": "Nachrichten löschen", "can_broadcast": "Broadcasts senden"}, available_permission_groups={"Basis-Moderation": {"can_warn": "Verwarnen", "can_delete": "Löschen"}})

@app.route("/id-finder/admin/add", methods=["POST"])
@login_required
def id_finder_add_admin():
    admins = load_json(ADMINS_FILE, {})
    admins[request.form.get("admin_id")] = {"name": request.form.get("admin_name"), "permissions": {}}
    save_json(ADMINS_FILE, admins)
    flash("Admin hinzugefügt.", "success")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/admin/delete", methods=["POST"])
@login_required
def id_finder_delete_admin():
    admins = load_json(ADMINS_FILE, {})
    if request.form.get("admin_id") in admins: del admins[request.form.get("admin_id")]
    save_json(ADMINS_FILE, admins)
    flash("Admin gelöscht.", "success")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/admin/update-perms", methods=["POST"])
@login_required
def id_finder_update_admin_permissions():
    admins = load_json(ADMINS_FILE, {})
    aid = request.form.get("admin_id")
    if aid in admins:
        admins[aid]["permissions"] = {k: True for k in request.form if k != "admin_id"}
        save_json(ADMINS_FILE, admins)
        flash("Rechte aktualisiert.", "success")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/user-detail/<user_id>")
@login_required
def user_detail(user_id):
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == int(user_id)).first()
        mod_logs = db.query(ModerationLog).filter(ModerationLog.user_id == user_id_int).order_by(ModerationLog.ts.desc()).all()
        
        if not user: abort(404)
        return render_template("id_finder_user_detail.html", user=user, mod_logs=mod_logs)

@app.route("/id-finder/delete-user/<user_id>", methods=["POST"])
@login_required
def id_finder_delete_user(user_id):
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user:
            db.delete(user)
            db.commit()
            flash("User gelöscht.", "success")
    return redirect(url_for("id_finder_dashboard"))

# --- BROADCAST MANAGER ---
@app.route("/broadcast")
@login_required
def broadcast_manager():
    with SessionLocal() as db:
        broadcasts = db.query(Broadcast).order_by(Broadcast.created_at.desc()).all()
        topics_db = db.query(Topic).all()
    # Convert list of SQL objects to a dict for the template
    topics_dict = {str(t.topic_id): t.name for t in topics_db}
    return render_template("broadcast_manager.html", broadcasts=broadcasts, known_topics=topics_dict)

@app.route("/broadcast/save", methods=["POST"])
@login_required
def save_broadcast():
    b_id = str(uuid.uuid4())
    media_file = request.files.get("media")
    media_name = None
    if media_file and media_file.filename:
        media_name = secure_filename(media_file.filename)
        media_file.save(os.path.join(app.config["UPLOAD_FOLDER"], media_name))
    with SessionLocal() as db:
        new_b = Broadcast(id=b_id, text=request.form.get("text"), topic_id=to_int(request.form.get("topic_id")), send_mode=request.form.get("send_mode"), scheduled_at=datetime.fromisoformat(request.form.get("scheduled_at")) if request.form.get("scheduled_at") else None, pin_message="pin_message" in request.form, silent_send="silent_send" in request.form, media_name=media_name, status="pending" if request.form.get("action") == "schedule" else "sent", created_at=datetime.utcnow())
        db.add(new_b)
        db.commit()
    flash("Broadcast gespeichert.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/delete/<broadcast_id>", methods=["POST"])
@login_required
def delete_broadcast(broadcast_id):
    with SessionLocal() as db:
        b = db.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
        if b:
            db.delete(b)
            db.commit()
            flash("Broadcast gelöscht.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topic/save", methods=["POST"])
@login_required
def save_topic_mapping():
    t_id = request.form.get("topic_id")
    t_name = request.form.get("topic_name")
    if t_id and t_name:
        with SessionLocal() as db:
            t = db.query(Topic).filter(Topic.topic_id == int(t_id)).first()
            if t:
                t.name = t_name
            else:
                new_t = Topic(chat_id=0, topic_id=int(t_id), name=t_name)
                db.add(new_t)
            db.commit()
        flash("Topic gespeichert.", "success")
    else:
        flash("Daten fehlen.", "danger")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topic/delete/<topic_id>", methods=["POST"])
@login_required
def delete_topic_mapping(topic_id):
    with SessionLocal() as db:
        t = db.query(Topic).filter(Topic.id == int(topic_id)).first()
        if t:
            db.delete(t)
            db.commit()
            flash("Topic gelöscht.", "success")
    return redirect(url_for("broadcast_manager"))

# --- OUTFIT BOT ---
@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    data = load_json(OUTFIT_BOT_DATA_FILE)
    duel = {"active": True, "contestants": " vs ".join([f"@{c['username']}" for c in data.get("current_duel", {}).get("contestants", {}).values()])} if data.get("current_duel") else {"active": False, "contestants": ""}
    return render_template("outfit_bot_dashboard.html", config=load_json(OUTFIT_BOT_CONFIG_FILE), is_running=get_bot_status()["outfit"]["running"], logs=open(OUTFIT_BOT_LOG_FILE).readlines()[-100:] if os.path.exists(OUTFIT_BOT_LOG_FILE) else [], duel_status=duel)

@app.route("/outfit-bot/action/<action>", methods=["POST"])
@login_required
def outfit_bot_actions(action):
    cfg = load_json(OUTFIT_BOT_CONFIG_FILE)
    if action == "save_config":
        cfg.update({"BOT_TOKEN": request.form.get("BOT_TOKEN"), "CHAT_ID": to_int(request.form.get("CHAT_ID")), "TOPIC_ID": to_int(request.form.get("TOPIC_ID")), "AUTO_POST_ENABLED": "AUTO_POST_ENABLED" in request.form, "POST_TIME": request.form.get("POST_TIME"), "WINNER_TIME": request.form.get("WINNER_TIME"), "DUEL_MODE": "DUEL_MODE" in request.form, "DUEL_TYPE": request.form.get("DUEL_TYPE"), "DUEL_DURATION_MINUTES": int(request.form.get("DUEL_DURATION_MINUTES", 60)), "ADMIN_USER_IDS": [x.strip() for x in request.form.get("ADMIN_USER_IDS", "").split(",") if x.strip()]})
        save_json(OUTFIT_BOT_CONFIG_FILE, cfg)
        flash("Konfiguration gespeichert.", "success")
    elif action == "clear_logs":
        if os.path.exists(OUTFIT_BOT_LOG_FILE): open(OUTFIT_BOT_LOG_FILE, 'w').close()
        flash("Logs geleert.", "success")
    return redirect(url_for("outfit_bot_dashboard"))

# --- MINECRAFT ---
@app.route("/minecraft")
@login_required
def minecraft_status_page():
    s = load_json(MINECRAFT_STATUS_CACHE_FILE)
    return render_template("minecraft.html", cfg=load_json(MINECRAFT_STATUS_CONFIG_FILE), status=s, is_running=get_bot_status()["minecraft"]["running"], server_online=s.get("online") is True, pi={"cpu_percent":0,"ram_used_mb":0,"temp_c":0,"disk_percent":0}, log_tail=open(MATCH_CONFIG["minecraft"]["log"]).read()[-2000:] if os.path.exists(MATCH_CONFIG["minecraft"]["log"]) else "")

@app.route("/minecraft/start", methods=["POST"])
@login_required
def minecraft_status_start(): return bot_action_route("minecraft", "start")

@app.route("/minecraft/stop", methods=["POST"])
@login_required
def minecraft_status_stop(): return bot_action_route("minecraft", "stop")

@app.route("/minecraft/save", methods=["POST"])
@login_required
def minecraft_status_save():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    cfg.update({"mc_host": request.form.get("mc_host"), "mc_port": int(request.form.get("mc_port", 25565)), "display_host": request.form.get("display_host"), "display_port": int(request.form.get("display_port", 25565)), "chat_id": to_int(request.form.get("chat_id")), "topic_id": to_int(request.form.get("topic_id"))})
    save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/reset-message", methods=["POST"])
@login_required
def minecraft_status_reset_message():
    cfg = load_json(MINECRAFT_STATUS_CONFIG_FILE)
    cfg["status_message_id"] = None
    save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    flash("Status-Nachricht zurückgesetzt. Bot sendet neu...", "success")
    return redirect(url_for("minecraft_status_page"))

# --- INVITE BOT ---
@app.route("/bot-settings", methods=["GET", "POST"])
@login_required
def bot_settings():
    if request.method == "POST":
        action = request.form.get("action")
        cfg = load_json(INVITE_BOT_CONFIG_FILE)
        if action == "save_base_config":
            cfg.update({"is_enabled": "is_enabled" in request.form, "bot_token": request.form.get("bot_token"), "main_chat_id": to_int(request.form.get("main_chat_id")), "topic_id": to_int(request.form.get("topic_id")), "link_ttl_minutes": int(request.form.get("link_ttl_minutes", 15))})
            save_json(INVITE_BOT_CONFIG_FILE, cfg)
            flash("Basis-Konfiguration gespeichert.", "success")
        elif action == "start_invite_bot": return bot_action_route("invite", "start")
        elif action == "stop_invite_bot": return bot_action_route("invite", "stop")
        return redirect(url_for("bot_settings"))
    return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE), is_invite_running=get_bot_status()["invite"]["running"], invite_bot_logs=open(INVITE_BOT_LOG_FILE).readlines()[-100:] if os.path.exists(INVITE_BOT_LOG_FILE) else [], user_interaction_logs=open(INVITE_BOT_INTERACTION_LOG).readlines()[-100:] if os.path.exists(INVITE_BOT_INTERACTION_LOG) else [])

@app.route("/bot-settings/save-content", methods=["POST"])
@login_required
def invite_bot_save_content():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    cfg.update({"start_message": request.form.get("start_message"), "rules_message": request.form.get("rules_message"), "blocked_message": request.form.get("blocked_message"), "privacy_policy": request.form.get("privacy_policy")})
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Texte gespeichert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/add-field", methods=["POST"])
@login_required
def invite_bot_add_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    cfg.setdefault("form_fields", []).append({"id": request.form.get("field_id"), "label": request.form.get("label"), "type": request.form.get("type"), "required": "required" in request.form, "enabled": True, "emoji": request.form.get("emoji"), "display_name": request.form.get("display_name"), "min_age": int(request.form.get("min_age")) if request.form.get("min_age") else None, "min_age_error_msg": request.form.get("min_age_error_msg")})
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Feld hinzugefügt.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/edit-field", methods=["POST"])
@login_required
def invite_bot_edit_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    for f in cfg.get("form_fields", []):
        if f["id"] == request.form.get("field_id"):
            f.update({"label": request.form.get("label"), "type": request.form.get("type"), "required": "required" in request.form, "enabled": "enabled" in request.form, "emoji": request.form.get("emoji"), "display_name": request.form.get("display_name"), "min_age": int(request.form.get("min_age")) if request.form.get("min_age") else None, "min_age_error_msg": request.form.get("min_age_error_msg")})
            break
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Feld aktualisiert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/delete-field", methods=["POST"])
@login_required
def invite_bot_delete_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    cfg["form_fields"] = [f for f in cfg.get("form_fields", []) if f["id"] != request.form.get("field_id")]
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Feld gelöscht.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/move-field/<field_id>/<direction>")
@login_required
def invite_bot_move_field(field_id, direction):
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    fields = cfg.get("form_fields", [])
    idx = next((i for i, f in enumerate(fields) if f["id"] == field_id), None)
    if idx is not None:
        if direction == "up" and idx > 0: fields[idx], fields[idx-1] = fields[idx-1], fields[idx]
        elif direction == "down" and idx < len(fields) - 1: fields[idx], fields[idx+1] = fields[idx+1], fields[idx]
        save_json(INVITE_BOT_CONFIG_FILE, cfg)
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/clear-logs/<log_type>", methods=["POST"])
@login_required
def invite_bot_clear_logs(log_type):
    file = INVITE_BOT_INTERACTION_LOG if log_type == "user" else INVITE_BOT_LOG_FILE
    if os.path.exists(file): open(file, 'w').close()
    flash("Logs geleert.", "success")
    return redirect(url_for("bot_settings"))

# --- QUIZ & UMFRAGE ---
@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    Q_FILE = os.path.join(DATA_DIR, "quizfragen.json")
    if request.method == "POST":
        action, cfg = request.form.get("action"), load_json(QUIZ_BOT_CONFIG_FILE)
        if action == "save_settings": cfg.update({"bot_token": request.form.get("token"), "channel_id": to_int(request.form.get("channel_id")), "topic_id": to_int(request.form.get("topic_id"))})
        elif action == "save_schedule": cfg["schedule"] = {"enabled": "schedule_enabled" in request.form, "time": request.form.get("schedule_time"), "days": [int(x) for x in request.form.getlist("schedule_days")]}
        elif action == "save_questions": save_json(Q_FILE, json.loads(request.form.get("questions_json")))
        save_json(QUIZ_BOT_CONFIG_FILE, cfg)
        flash("Gespeichert.", "success")
        return redirect(url_for("quiz_settings"))
    qs = load_json(Q_FILE, [])
    return render_template("quiz_settings.html", config=load_json(QUIZ_BOT_CONFIG_FILE), schedule=load_json(QUIZ_BOT_CONFIG_FILE).get("schedule", {}), stats={"total": len(qs), "asked": 0, "remaining": len(qs)}, questions_json=json.dumps(qs, indent=4, ensure_ascii=False), asked_questions_json="[]", logs=[])

@app.route("/umfrage-settings", methods=["GET", "POST"])
@login_required
def umfrage_settings():
    U_FILE = os.path.join(DATA_DIR, "umfragen.json")
    if request.method == "POST":
        action, cfg = request.form.get("action"), load_json(UMFRAGE_BOT_CONFIG_FILE)
        if action == "save_settings": cfg.update({"bot_token": request.form.get("token"), "channel_id": to_int(request.form.get("channel_id")), "topic_id": to_int(request.form.get("topic_id"))})
        elif action == "save_schedule": cfg["schedule"] = {"enabled": "schedule_enabled" in request.form, "time": request.form.get("schedule_time"), "days": [int(x) for x in request.form.getlist("schedule_days")]}
        elif action == "save_umfragen": save_json(U_FILE, json.loads(request.form.get("umfragen_json")))
        save_json(UMFRAGE_BOT_CONFIG_FILE, cfg)
        flash("Gespeichert.", "success")
        return redirect(url_for("umfrage_settings"))
    us = load_json(U_FILE, [])
    return render_template("umfrage_settings.html", config=load_json(UMFRAGE_BOT_CONFIG_FILE), schedule=load_json(UMFRAGE_BOT_CONFIG_FILE).get("schedule", {}), stats={"total": len(us), "asked": 0, "remaining": len(us)}, umfragen_json=json.dumps(us, indent=4, ensure_ascii=False), asked_umfragen_json="[]", logs=[])

@app.route("/quiz/send-random", methods=["POST"])
@login_required
def quiz_send_random():
    with open(os.path.join(BOTS_DIR, "quiz_bot", "command_send_random.tmp"), "w") as f: f.write("1")
    flash("Befehl gesendet.", "info")
    return redirect(request.referrer or url_for("index"))

@app.route("/umfrage/send-random", methods=["POST"])
@login_required
def umfrage_send_random():
    with open(os.path.join(BOTS_DIR, "umfrage_bot", "command_send_random.tmp"), "w") as f: f.write("1")
    flash("Befehl gesendet.", "info")
    return redirect(request.referrer or url_for("index"))

# --- USER MANAGEMENT ---
@app.route("/admin/users")
@login_required
def manage_users(): return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user():
    u, p, r = request.form.get("username"), request.form.get("password"), request.form.get("role")
    users = load_json(USERS_FILE, {})
    if u in users: flash("Existiert bereits.", "danger")
    else:
        users[u] = {"password": generate_password_hash(p), "role": r}
        save_json(USERS_FILE, users)
        flash("User erstellt.", "success")
    return redirect(url_for("manage_users"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
@login_required
def delete_user(username):
    users = load_json(USERS_FILE, {})
    if username in users:
        del users[username]
        save_json(USERS_FILE, users)
        flash("User gelöscht.", "success")
    return redirect(url_for("manage_users"))

@app.route("/admin/users/edit/<username>", methods=["POST"])
@login_required
def edit_user(username):
    users = load_json(USERS_FILE, {})
    if username in users:
        u_data = users.pop(username)
        if request.form.get("new_password"): u_data["password"] = generate_password_hash(request.form.get("new_password"))
        u_data["role"] = request.form.get("new_role")
        users[request.form.get("new_username") or username] = u_data
        save_json(USERS_FILE, users)
        flash("Aktualisiert.", "success")
    return redirect(url_for("manage_users"))

# --- SYSTEM ---
@app.route("/bot-action/<bot_name>/<action>", methods=["POST"])
@login_required
def bot_action_route(bot_name, action):
    cfg = MATCH_CONFIG.get(bot_name)
    if not cfg: return redirect(url_for("index"))
    if action == "start": subprocess.Popen([VENV_PYTHON, cfg["script"]], cwd=os.path.dirname(cfg["script"]), stdout=open(cfg["log"], "a"), stderr=subprocess.STDOUT)
    elif action == "stop": subprocess.run(["pkill", "-f", cfg["pattern"]])
    return redirect(request.referrer or url_for("index"))

@app.route("/critical-errors")
@login_required
def critical_errors(): return render_template("critical_errors.html", critical_logs=open(CRITICAL_ERRORS_LOG_FILE).readlines() if os.path.exists(CRITICAL_ERRORS_LOG_FILE) else [])

@app.route("/critical-errors/clear", methods=["POST"])
@login_required
def clear_critical_errors():
    if os.path.exists(CRITICAL_ERRORS_LOG_FILE): open(CRITICAL_ERRORS_LOG_FILE, 'w').close()
    flash("Logs gelöscht.", "success")
    return redirect(url_for("critical_errors"))

@app.route("/api/update/check")
@login_required
def update_check(): return jsonify(get_updater().check_for_update() if get_updater() else {"update_available": False})

@app.route("/api/update/install", methods=["POST"])
@login_required
def update_install():
    u, data = get_updater(), request.json
    if u: u.install_update(data.get("zipball_url"), data.get("latest_version"), data.get("published_at"))
    return jsonify({"status": "started"})

@app.route("/api/update/status")
@login_required
def update_status(): return jsonify(get_updater().get_status() if get_updater() else {"status": "idle"})

@app.route("/tg/avatar/<user_id>")
def tg_avatar_proxy(user_id):
    try:
        # Prio 1: ID Finder Token
        cfg = load_json(ID_FINDER_CONFIG_FILE)
        token = cfg.get("bot_token")
        
        # Prio 2: Quiz/Umfrage Token (Fallback)
        if not token:
            cfg2 = load_json(DASHBOARD_CONFIG_FILE)
            token = cfg2.get("quiz", {}).get("token") or cfg2.get("umfrage", {}).get("token")

        if not token: abort(404)
        
        res = requests.get(f"https://api.telegram.org/bot{token}/getUserProfilePhotos?user_id={user_id}&limit=1")
        if res.status_code != 200: abort(404)
        data = res.json()
        if not data.get("result") or not data["result"]["photos"]: abort(404)
        
        # Get the smallest photo for avatar
        photo_list = data["result"]["photos"][0]
        file_id = photo_list[0]["file_id"] # small
        
        res = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}")
        if res.status_code != 200: abort(404)
        file_path = res.json()["result"]["file_path"]
        
        # Redirect to Telegram file content
        return redirect(f"https://api.telegram.org/file/bot{token}/{file_path}")
    except Exception as e:
        log.error(f"Avatar proxy error: {e}")
        abort(404)

@app.route("/tg/media/<file_id>")
def tg_media_proxy(file_id):
    try:
        cfg = load_json(ID_FINDER_CONFIG_FILE)
        token = cfg.get("bot_token")
        
        if not token:
             cfg2 = load_json(DASHBOARD_CONFIG_FILE)
             token = cfg2.get("quiz", {}).get("token")

        if not token: abort(404)
        
        res = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}")
        if res.status_code != 200: abort(404)
        file_path = res.json()["result"]["file_path"]
        
        return redirect(f"https://api.telegram.org/file/bot{token}/{file_path}")
    except Exception as e:
        log.error(f"Media proxy error: {e}")
        abort(404)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9002, debug=True)
