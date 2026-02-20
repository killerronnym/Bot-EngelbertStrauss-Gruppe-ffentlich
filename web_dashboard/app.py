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

def get_bot_status():
    try:
        output = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True, check=False).stdout
        return {k: {"running": cfg["pattern"] in output} for k, cfg in MATCH_CONFIG.items()}
    except: return {k: {"running": False} for k in MATCH_CONFIG}

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

# --- AUTH ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session: return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get("username"), request.form.get("password")
        users = load_json(USERS_FILE, {})
        if u in users and check_password_hash(users[u]["password"], p):
            session["user"], session["role"] = u, users[u].get("role", "admin")
            return redirect(url_for("index"))
        flash("Fehler.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

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

@app.route("/id-finder")
@login_required
def id_finder_dashboard(): return render_template("id_finder_dashboard.html", config=load_json(ID_FINDER_CONFIG_FILE))

@app.route("/broadcast")
@login_required
def broadcast_manager(): return render_template("broadcast_manager.html", broadcasts=load_json(BROADCAST_DATA_FILE, []), known_topics=load_json(TOPIC_REGISTRY_FILE, {}))

@app.route("/outfit-bot/dashboard")
@login_required
def outfit_bot_dashboard():
    data = load_json(OUTFIT_BOT_DATA_FILE)
    duel = {"active": True, "contestants": " vs ".join([f"@{c['username']}" for c in data["current_duel"]["contestants"].values()])} if data.get("current_duel") else {"active": False, "contestants": ""}
    return render_template("outfit_bot_dashboard.html", config=load_json(OUTFIT_BOT_CONFIG_FILE), is_running=get_bot_status()["outfit"]["running"], logs=open(OUTFIT_BOT_LOG_FILE).readlines()[-100:] if os.path.exists(OUTFIT_BOT_LOG_FILE) else [], duel_status=duel)

@app.route("/minecraft")
@login_required
def minecraft_status_page():
    s = load_json(MINECRAFT_STATUS_CACHE_FILE)
    return render_template("minecraft.html", cfg=load_json(MINECRAFT_STATUS_CONFIG_FILE), status=s, is_running=get_bot_status()["minecraft"]["running"], server_online=s.get("online") is True, pi={"cpu_percent":0,"ram_used_mb":0,"temp_c":0,"disk_percent":0}, log_tail=open(MATCH_CONFIG["minecraft"]["log"]).read()[-2000:] if os.path.exists(MATCH_CONFIG["minecraft"]["log"]) else "")

@app.route("/admin/users")
@login_required
def manage_users(): return render_template("manage_users.html", users=load_json(USERS_FILE, {}))

@app.route("/critical-errors")
@login_required
def critical_errors(): return render_template("critical_errors.html", critical_logs=open(CRITICAL_ERRORS_LOG_FILE).readlines() if os.path.exists(CRITICAL_ERRORS_LOG_FILE) else [])

@app.route("/bot-settings")
@login_required
def bot_settings(): return render_template("bot_settings.html", config=load_json(INVITE_BOT_CONFIG_FILE))

@app.route("/quiz-settings", methods=["GET", "POST"])
@login_required
def quiz_settings():
    Q_FILE = os.path.join(DATA_DIR, "quizfragen.json")
    if request.method == "POST":
        action, cfg = request.form.get("action"), load_json(QUIZ_BOT_CONFIG_FILE)
        if action == "save_settings": cfg.update({"bot_token": request.form.get("token"), "channel_id": request.form.get("channel_id"), "topic_id": request.form.get("topic_id")})
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
        if action == "save_settings": cfg.update({"bot_token": request.form.get("token"), "channel_id": request.form.get("channel_id"), "topic_id": request.form.get("topic_id")})
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9002, debug=True)
