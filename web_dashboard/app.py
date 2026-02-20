import os
import json
import logging
from logging.handlers import RotatingFileHandler
import atexit
import subprocess
import sys
import shutil
import signal
import re
import threading
import time
import socket
from datetime import datetime, timedelta
from collections import defaultdict, deque
import io

# ✅ Pfad-Fix für Module im gleichen Verzeichnis
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ✅ Telegram Proxy Cache
import hashlib
import mimetypes
import urllib.parse
import urllib.request
import urllib.error

# ✅ Updater Integration
from updater import Updater

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from flask import (
    Flask, render_template, request, flash, redirect, url_for, jsonify, render_template_string, send_file, abort, session
)
from jinja2 import TemplateNotFound
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s", handlers=[RotatingFileHandler("app.log", maxBytes=10240, backupCount=5), logging.StreamHandler(sys.stdout)], force=True)
log = logging.getLogger(__name__)

CRITICAL_ERRORS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "critical_errors.log")
critical_errors_handler = RotatingFileHandler(CRITICAL_ERRORS_LOG_FILE, maxBytes=10240, backupCount=2)
critical_errors_handler.setLevel(logging.ERROR)
critical_errors_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"))
logging.getLogger().addHandler(critical_errors_handler)

app = Flask(__name__, template_folder="src")
app.secret_key = "b13f172933b9a1274adb024d47fc7552d2e85864693cb9a2"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# --- Pfade ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BOTS_DIR = os.path.join(PROJECT_ROOT, "bots")
VERSION_FILE = os.path.join(PROJECT_ROOT, "version.json")
DASHBOARD_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
TOPIC_CONFIG_FILE = os.path.join(BASE_DIR, "topic_config.json")
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.jsonl")
USER_REGISTRY_FILE = os.path.join(DATA_DIR, "user_registry.json")
MODERATION_CONFIG_FILE = os.path.join(DATA_DIR, "moderation_config.json")
MODERATION_DATA_FILE = os.path.join(DATA_DIR, "moderation_data.json")
BROADCAST_DATA_FILE = os.path.join(DATA_DIR, "scheduled_broadcasts.json")
TOPIC_REGISTRY_FILE = os.path.join(DATA_DIR, "topic_registry.json")
MINECRAFT_STATUS_CONFIG_FILE = os.path.join(DATA_DIR, "minecraft_status_config.json")
MINECRAFT_STATUS_CACHE_FILE = os.path.join(DATA_DIR, "minecraft_status_cache.json")
QUIZ_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "quiz_bot", "quiz_bot_config.json")
UMFRAGE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "umfrage_bot", "umfrage_bot_config.json")
INVITE_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "invite_bot", "invite_bot_config.json")
INVITE_BOT_LOG_FILE = os.path.join(BOTS_DIR, "invite_bot", "invite_bot.log")
INVITE_BOT_INTERACTION_LOG = os.path.join(BOTS_DIR, "invite_bot", "user_interactions.log")
OUTFIT_BOT_CONFIG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_config.json")
OUTFIT_BOT_DATA_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot_data.json")
OUTFIT_BOT_LOG_FILE = os.path.join(BOTS_DIR, "outfit_bot", "outfit_bot.log")
ID_FINDER_CONFIG_FILE = os.path.join(BOTS_DIR, "id_finder_bot", "id_finder_config.json")

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

# --- Helpers ---
def load_json(path, default=None):
    if not os.path.exists(path): return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def to_int(val, default=None):
    if val is None or val == "" or str(val).lower() == "null": return default
    try: return int(val)
    except: return default

def get_bot_status():
    try:
        output = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True, check=False).stdout
        return {k: {"running": cfg["pattern"] in output} for k, cfg in MATCH_CONFIG.items()}
    except: return {k: {"running": False} for k in MATCH_CONFIG}

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%H:%M:%S | %d.%m.%Y'):
    if value is None: return ""
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value)
        else:
            dt = datetime.fromisoformat(value)
        return dt.strftime(format)
    except: return str(value)

@app.context_processor
def inject_globals():
    return {"bot_status": get_bot_status()}

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
        if not os.path.exists(VERSION_FILE): save_json(VERSION_FILE, {"version": "3.0.0", "release_date": datetime.now().isoformat()})
        flash("Setup abgeschlossen!", "success")
        return redirect(url_for("login"))
    return render_template("setup.html")

# --- AUTH (Deaktiviert) ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            session["user"] = "Gast-Admin"
            session["role"] = "admin"
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    session["user"] = "Gast-Admin"
    session["role"] = "admin"
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# --- UPDATER ---
def get_updater():
    if not is_setup_done(): return None
    c = load_json(DASHBOARD_CONFIG_FILE)
    return Updater(repo_owner=c.get("github_owner"), repo_name=c.get("github_repo"), current_version_file=VERSION_FILE, project_root=PROJECT_ROOT)

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

# --- MAIN DASHBOARD & ROUTES ---
@app.route("/")
@login_required
def index(): return render_template("index.html", version=load_json(VERSION_FILE, {"version": "3.0.0"}))

@app.route("/live-moderation")
@login_required
def live_moderation():
    chat_id = request.args.get("chat_id")
    topic_id = request.args.get("topic_id")
    messages = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-100:]
            for line in lines:
                try:
                    msg = json.loads(line)
                    if not chat_id or str(msg.get("chat_id")) == str(chat_id):
                        if not topic_id or str(msg.get("thread_id")) == str(topic_id) or topic_id == "all":
                            messages.append(msg)
                except: continue
    messages.reverse()
    return render_template("live_moderation.html", 
                           messages=messages, 
                           topics=load_json(TOPIC_REGISTRY_FILE, {}), 
                           mod_config=load_json(MODERATION_CONFIG_FILE, {}),
                           selected_chat_id=chat_id,
                           selected_topic_id=topic_id)

@app.route("/live-moderation/config", methods=["POST"])
@login_required
def live_moderation_config():
    config = {
        "max_warnings": int(request.form.get("max_warnings", 3)),
        "warning_text": request.form.get("warning_text", ""),
        "public_delete_notice_text": request.form.get("public_delete_notice_text", ""),
        "public_delete_notice_duration": int(request.form.get("public_delete_notice_duration", 60))
    }
    save_json(MODERATION_CONFIG_FILE, config)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("live_moderation"))

@app.route("/live-moderation/delete", methods=["POST"])
@login_required
def live_moderation_delete():
    flash("Aktion vorgemerkt (Signal an Bot).", "info")
    return redirect(url_for("live_moderation"))

@app.route("/user-detail/<user_id>")
@login_required
def user_detail(user_id):
    registry = load_json(USER_REGISTRY_FILE, {})
    user_data = registry.get(str(user_id), {"user_id": user_id, "full_name": "Unbekannt", "username": "N/A"})
    return render_template("id_finder_user_detail.html", user=user_data)

# --- ID FINDER ROUTES ---
@app.route("/id-finder")
@login_required
def id_finder_dashboard():
    registry = load_json(USER_REGISTRY_FILE, [])
    if isinstance(registry, dict):
        registry = [{"id": k, **v} for k, v in registry.items()]
    return render_template("id_finder_dashboard.html", 
                           config=load_json(ID_FINDER_CONFIG_FILE),
                           is_running=get_bot_status()["id_finder"]["running"],
                           user_registry=registry)

@app.route("/id-finder/save-config", methods=["POST"])
@login_required
def id_finder_save_config():
    cfg = load_json(ID_FINDER_CONFIG_FILE)
    cfg.update({
        "bot_token": request.form.get("bot_token"),
        "admin_group_id": to_int(request.form.get("admin_group_id")),
        "main_group_id": to_int(request.form.get("main_group_id")),
        "admin_log_topic_id": to_int(request.form.get("admin_log_topic_id")),
        "delete_commands": "delete_commands" in request.form,
        "bot_message_cleanup_seconds": int(request.form.get("bot_message_cleanup_seconds", 0)),
        "message_logging_enabled": "message_logging_enabled" in request.form,
        "message_logging_ignore_commands": "message_logging_ignore_commands" in request.form,
        "message_logging_groups_only": "message_logging_groups_only" in request.form
    })
    save_json(ID_FINDER_CONFIG_FILE, cfg)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("id_finder_dashboard"))

@app.route("/id-finder/commands")
@login_required
def id_finder_commands(): return render_template("id_finder_commands.html")

@app.route("/id-finder/admin-panel")
@login_required
def id_finder_admin_panel(): 
    return render_template("id_finder_admin_panel.html", 
                           admins=load_json(ADMINS_FILE, {}),
                           available_permissions={"can_warn": "Nutzer verwarnen", "can_delete": "Nachrichten löschen", "can_broadcast": "Broadcasts senden"},
                           available_permission_groups={"Basis-Moderation": {"can_warn": "Verwarnen", "can_delete": "Löschen"}})

@app.route("/id-finder/admin/add", methods=["POST"])
@login_required
def id_finder_add_admin():
    admins = load_json(ADMINS_FILE, {})
    aid = request.form.get("admin_id")
    admins[aid] = {"name": request.form.get("admin_name"), "permissions": {}}
    save_json(ADMINS_FILE, admins)
    flash("Admin hinzugefügt.", "success")
    return redirect(url_for("id_finder_admin_panel"))

@app.route("/id-finder/admin/delete", methods=["POST"])
@login_required
def id_finder_delete_admin():
    admins = load_json(ADMINS_FILE, {})
    aid = request.form.get("admin_id")
    if aid in admins: del admins[aid]
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

@app.route("/id-finder/analytics")
@login_required
def id_finder_analytics(): 
    registry = load_json(USER_REGISTRY_FILE, {})
    stats = {"total_users": len(registry)}
    activity = {
        "leaderboard": [],
        "timeline": {"labels": [], "total": []},
        "busiest_hours": [0]*24,
        "busiest_days": [0]*7
    }
    return render_template("id_finder_analytics.html", stats=stats, activity=activity)

@app.route("/id-finder/user/<user_id>")
@login_required
def id_finder_user_detail(user_id):
    registry = load_json(USER_REGISTRY_FILE, {})
    user_data = registry.get(str(user_id), {"user_id": user_id, "full_name": "Unbekannt", "username": "N/A"})
    return render_template("id_finder_user_detail.html", user=user_data)

@app.route("/id-finder/delete-user/<user_id>", methods=["POST"])
@login_required
def id_finder_delete_user(user_id):
    registry = load_json(USER_REGISTRY_FILE, {})
    if str(user_id) in registry:
        del registry[str(user_id)]
        save_json(USER_REGISTRY_FILE, registry)
        flash("User gelöscht.", "success")
    return redirect(url_for("id_finder_dashboard"))
# --- END ID FINDER ROUTES ---

# --- BROADCAST MANAGER ROUTES ---
@app.route("/broadcast")
@login_required
def broadcast_manager(): return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))

@app.route("/broadcast/save", methods=["POST"])
@login_required
def save_broadcast():
    broadcasts = load_json(BROADCAST_DATA_FILE, [])
    b_id = str(uuid.uuid4())
    media_file = request.files.get("media")
    media_name = None
    if media_file and media_file.filename:
        media_name = secure_filename(media_file.filename)
        media_file.save(os.path.join(app.config["UPLOAD_FOLDER"], media_name))
    
    new_b = {
        "id": b_id,
        "text": request.form.get("text"),
        "topic_id": to_int(request.form.get("topic_id")),
        "send_mode": request.form.get("send_mode"),
        "scheduled_at": request.form.get("scheduled_at"),
        "pin_message": "pin_message" in request.form,
        "silent_send": "silent_send" in request.form,
        "media_name": media_name,
        "status": "pending" if request.form.get("action") == "schedule" else "sent",
        "created_at": datetime.now().isoformat()
    }
    broadcasts.append(new_b)
    save_json(BROADCAST_DATA_FILE, broadcasts)
    flash("Broadcast gespeichert/gesendet.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/delete/<broadcast_id>", methods=["POST"])
@login_required
def delete_broadcast(broadcast_id):
    broadcasts = load_json(BROADCAST_DATA_FILE, [])
    broadcasts = [b for b in broadcasts if b["id"] != broadcast_id]
    save_json(BROADCAST_DATA_FILE, broadcasts)
    flash("Broadcast gelöscht.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topic/save", methods=["POST"])
@login_required
def save_topic_mapping():
    topics = load_json(TOPIC_REGISTRY_FILE, {})
    topics[request.form.get("topic_id")] = request.form.get("topic_name")
    save_json(TOPIC_REGISTRY_FILE, topics)
    flash("Topic gespeichert.", "success")
    return redirect(url_for("broadcast_manager"))

@app.route("/broadcast/topic/delete/<topic_id>", methods=["POST"])
@login_required
def delete_topic_mapping(topic_id):
    topics = load_json(TOPIC_REGISTRY_FILE, {})
    if topic_id in topics: del topics[topic_id]
    save_json(TOPIC_REGISTRY_FILE, topics)
    flash("Topic gelöscht.", "success")
    return redirect(url_for("broadcast_manager"))
# --- END BROADCAST MANAGER ROUTES ---

# --- OUTFIT BOT ROUTES ---
@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    data = load_json(OUTFIT_BOT_DATA_FILE)
    duel = {"active": True, "contestants": " vs ".join([f"@{c['username']}" for c in data["current_duel"]["contestants"].values()])} if data.get("current_duel") else {"active": False, "contestants": ""}
    return render_template("outfit_bot_dashboard.html", config=load_json(OUTFIT_BOT_CONFIG_FILE), is_running=get_bot_status()["outfit"]["running"], logs=open(OUTFIT_BOT_LOG_FILE).readlines()[-100:] if os.path.exists(OUTFIT_BOT_LOG_FILE) else [], duel_status=duel)

@app.route("/outfit-bot/action/<action>", methods=["POST"])
@login_required
def outfit_bot_actions(action):
    cfg = load_json(OUTFIT_BOT_CONFIG_FILE)
    if action == "save_config":
        cfg.update({
            "BOT_TOKEN": request.form.get("BOT_TOKEN"),
            "CHAT_ID": to_int(request.form.get("CHAT_ID")),
            "TOPIC_ID": to_int(request.form.get("TOPIC_ID")),
            "AUTO_POST_ENABLED": "AUTO_POST_ENABLED" in request.form,
            "POST_TIME": request.form.get("POST_TIME"),
            "WINNER_TIME": request.form.get("WINNER_TIME"),
            "DUEL_MODE": "DUEL_MODE" in request.form,
            "DUEL_TYPE": request.form.get("DUEL_TYPE"),
            "DUEL_DURATION_MINUTES": int(request.form.get("DUEL_DURATION_MINUTES", 60)),
            "ADMIN_USER_IDS": [x.strip() for x in request.form.get("ADMIN_USER_IDS", "").split(",") if x.strip()]
        })
        save_json(OUTFIT_BOT_CONFIG_FILE, cfg)
        flash("Konfiguration gespeichert.", "success")
        if get_bot_status()["outfit"]["running"]:
            subprocess.run(["pkill", "-f", MATCH_CONFIG["outfit"]["pattern"]])
            time.sleep(1)
            subprocess.Popen([VENV_PYTHON, MATCH_CONFIG["outfit"]["script"]], cwd=os.path.dirname(MATCH_CONFIG["outfit"]["script"]), stdout=open(MATCH_CONFIG["outfit"]["log"], "a"), stderr=subprocess.STDOUT)
    elif action == "start_contest":
        with open(os.path.join(BOTS_DIR, "outfit_bot", "cmd_start_contest.tmp"), "w") as f: f.write("1")
        flash("Befehl 'Wettbewerb starten' gesendet.", "info")
    elif action == "announce_winner":
        with open(os.path.join(BOTS_DIR, "outfit_bot", "cmd_announce_winner.tmp"), "w") as f: f.write("1")
        flash("Befehl 'Gewinner auslosen' gesendet.", "info")
    elif action == "end_duel":
        with open(os.path.join(BOTS_DIR, "outfit_bot", "cmd_end_duel.tmp"), "w") as f: f.write("1")
        flash("Befehl 'Duell beenden' gesendet.", "info")
    elif action == "clear_logs":
        if os.path.exists(OUTFIT_BOT_LOG_FILE): open(OUTFIT_BOT_LOG_FILE, 'w').close()
        flash("Logs geleert.", "success")
    
    return redirect(url_for("outfit_bot_dashboard"))
# --- END OUTFIT BOT ROUTES ---

# --- MINECRAFT ROUTES ---
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
    cfg.update({
        "mc_host": request.form.get("mc_host"),
        "mc_port": int(request.form.get("mc_port", 25565)),
        "display_host": request.form.get("display_host"),
        "display_port": int(request.form.get("display_port", 25565)),
        "chat_id": to_int(request.form.get("chat_id")),
        "topic_id": to_int(request.form.get("topic_id"))
    })
    save_json(MINECRAFT_STATUS_CONFIG_FILE, cfg)
    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("minecraft_status_page"))

@app.route("/minecraft/reset-message", methods=["POST"])
@login_required
def minecraft_status_reset_message():
    flash("Nachricht wird beim nächsten Update neu erstellt.", "info")
    return redirect(url_for("minecraft_status_page"))
# --- END MINECRAFT ROUTES ---

# --- USER MANAGEMENT ROUTES ---
@app.route("/admin/users")
@login_required
def manage_users(): return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/admin/users/add", methods=["POST"])
@login_required
def add_user():
    u, p, r = request.form.get("username"), request.form.get("password"), request.form.get("role")
    users = load_json(USERS_FILE, {})
    if u in users: flash("User existiert bereits.", "danger")
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
        new_u = request.form.get("new_username")
        new_p = request.form.get("new_password")
        new_r = request.form.get("new_role")
        
        user_data = users.pop(username)
        if new_p: user_data["password"] = generate_password_hash(new_p)
        user_data["role"] = new_r
        
        final_u = new_u if new_u else username
        users[final_u] = user_data
        save_json(USERS_FILE, users)
        flash("User aktualisiert.", "success")
    return redirect(url_for("manage_users"))
# --- END USER MANAGEMENT ROUTES ---

@app.route("/critical-errors")
@login_required
def critical_errors(): return render_template("critical_errors.html", critical_logs=open(CRITICAL_ERRORS_LOG_FILE).readlines() if os.path.exists(CRITICAL_ERRORS_LOG_FILE) else [])

@app.route("/critical-errors/clear", methods=["POST"])
@login_required
def clear_critical_errors():
    if os.path.exists(CRITICAL_ERRORS_LOG_FILE): open(CRITICAL_ERRORS_LOG_FILE, 'w').close()
    flash("Logs gelöscht.", "success")
    return redirect(url_for("critical_errors"))

# --- INVITE BOT ROUTES ---
@app.route("/bot-settings", methods=["GET", "POST"])
@login_required
def bot_settings():
    if request.method == "POST":
        action = request.form.get("action")
        cfg = load_json(INVITE_BOT_CONFIG_FILE)
        if action == "save_base_config":
            cfg.update({
                "is_enabled": "is_enabled" in request.form,
                "bot_token": request.form.get("bot_token"),
                "main_chat_id": to_int(request.form.get("main_chat_id")),
                "topic_id": to_int(request.form.get("topic_id")),
                "link_ttl_minutes": int(request.form.get("link_ttl_minutes", 15))
            })
            save_json(INVITE_BOT_CONFIG_FILE, cfg)
            flash("Basis-Konfiguration gespeichert.", "success")
        elif action == "start_invite_bot":
            return bot_action_route("invite", "start")
        elif action == "stop_invite_bot":
            return bot_action_route("invite", "stop")
        return redirect(url_for("bot_settings"))
    
    return render_template("bot_settings.html", 
                           config=load_json(INVITE_BOT_CONFIG_FILE), 
                           is_invite_running=get_bot_status()["invite"]["running"],
                           invite_bot_logs=open(INVITE_BOT_LOG_FILE).readlines()[-100:] if os.path.exists(INVITE_BOT_LOG_FILE) else [],
                           user_interaction_logs=open(INVITE_BOT_INTERACTION_LOG).readlines()[-100:] if os.path.exists(INVITE_BOT_INTERACTION_LOG) else [])

@app.route("/bot-settings/save-content", methods=["POST"])
@login_required
def invite_bot_save_content():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    cfg.update({
        "start_message": request.form.get("start_message"),
        "rules_message": request.form.get("rules_message"),
        "blocked_message": request.form.get("blocked_message"),
        "privacy_policy": request.form.get("privacy_policy")
    })
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Texte gespeichert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/add-field", methods=["POST"])
@login_required
def invite_bot_add_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    new_field = {
        "id": request.form.get("field_id"),
        "label": request.form.get("label"),
        "type": request.form.get("type"),
        "required": "required" in request.form,
        "enabled": True,
        "emoji": request.form.get("emoji"),
        "display_name": request.form.get("display_name"),
        "min_age": int(request.form.get("min_age")) if request.form.get("min_age") else None,
        "min_age_error_msg": request.form.get("min_age_error_msg")
    }
    cfg.setdefault("form_fields", []).append(new_field)
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Feld hinzugefügt.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/edit-field", methods=["POST"])
@login_required
def invite_bot_edit_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    fid = request.form.get("field_id")
    for field in cfg.get("form_fields", []):
        if field["id"] == fid:
            field.update({
                "label": request.form.get("label"),
                "type": request.form.get("type"),
                "required": "required" in request.form,
                "enabled": "enabled" in request.form,
                "emoji": request.form.get("emoji"),
                "display_name": request.form.get("display_name"),
                "min_age": int(request.form.get("min_age")) if request.form.get("min_age") else None,
                "min_age_error_msg": request.form.get("min_age_error_msg")
            })
            break
    save_json(INVITE_BOT_CONFIG_FILE, cfg)
    flash("Feld aktualisiert.", "success")
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/delete-field", methods=["POST"])
@login_required
def invite_bot_delete_field():
    cfg = load_json(INVITE_BOT_CONFIG_FILE)
    fid = request.form.get("field_id")
    cfg["form_fields"] = [f for f in cfg.get("form_fields", []) if f["id"] != fid]
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
        if direction == "up" and idx > 0:
            fields[idx], fields[idx-1] = fields[idx-1], fields[idx]
        elif direction == "down" and idx < len(fields) - 1:
            fields[idx], fields[idx+1] = fields[idx+1], fields[idx]
        save_json(INVITE_BOT_CONFIG_FILE, cfg)
    return redirect(url_for("bot_settings"))

@app.route("/bot-settings/clear-logs/<log_type>", methods=["POST"])
@login_required
def invite_bot_clear_logs(log_type):
    file = INVITE_BOT_INTERACTION_LOG if log_type == "user" else INVITE_BOT_LOG_FILE
    if os.path.exists(file): open(file, 'w').close()
    flash("Logs geleert.", "success")
    return redirect(url_for("bot_settings"))

# --- END INVITE BOT ROUTES ---

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

@app.route("/bot-action/<bot_name>/<action>", methods=["POST"])
@login_required
def bot_action_route(bot_name, action):
    cfg = MATCH_CONFIG.get(bot_name)
    if not cfg: return redirect(url_for("index"))
    if action == "start": subprocess.Popen([VENV_PYTHON, cfg["script"]], cwd=os.path.dirname(cfg["script"]), stdout=open(cfg["log"], "a"), stderr=subprocess.STDOUT)
    elif action == "stop": subprocess.run(["pkill", "-f", cfg["pattern"]])
    return redirect(request.referrer or url_for("index"))

@app.route("/quiz/send-random", methods=["POST"])
@login_required
def quiz_send_random():
    with open(os.path.join(BOTS_DIR, "quiz_bot", "command_send_random.tmp"), "w") as f: f.write("1")
    return redirect(request.referrer or url_for("index"))

@app.route("/umfrage/send-random", methods=["POST"])
@login_required
def umfrage_send_random():
    with open(os.path.join(BOTS_DIR, "umfrage_bot", "command_send_random.tmp"), "w") as f: f.write("1")
    return redirect(request.referrer or url_for("index"))

@app.route("/tg/avatar/<user_id>")
def tg_avatar_proxy(user_id):
    p = os.path.join(DATA_DIR, "avatars", f"{user_id}.jpg")
    return send_file(p) if os.path.exists(p) else abort(404)

@app.route("/tg/media/<file_id>")
def tg_media_proxy(file_id):
    return abort(404)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9002, debug=True)
