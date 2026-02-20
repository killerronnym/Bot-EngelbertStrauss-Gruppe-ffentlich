# 📥 Installation & Setup (SQL Version)

Diese Anleitung hilft dir, das Bot-System mit der neuen SQL-Datenbank auf deinem Server oder NAS zu installieren.

## 📋 Voraussetzungen

*   **Python 3.10+**
*   **pip** (Python Package Installer)
*   **Virtual Environment** (empfohlen)
*   **SQLite3** (standardmäßig in Python enthalten)

## 🚀 Installation

1.  **Repository klonen oder Dateien kopieren.**
2.  **Virtuelle Umgebung erstellen:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
3.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```
    *Hinweis: Dies installiert nun auch `sqlalchemy` und `flask-sqlalchemy` für die Datenbank.*

4.  **Datenbank initialisieren:**
    Das System erstellt die Datenbank automatisch beim ersten Start. Du kannst es aber auch manuell testen:
    ```bash
    python3 -c "from database import init_db; init_db()"
    ```
    Es sollte nun eine Datei `data/bot_database.db` existieren.

## 🖥️ Dashboard starten

Das Dashboard ist die zentrale Steuereinheit.
```bash
./devserver.sh
```
Oder manuell via Gunicorn (Produktion):
```bash
gunicorn --bind 0.0.0.0:9002 web_dashboard.app:app
```

## 🛡️ Stabilität & Sicherheit

*   **SQL-Datenbank:** Alle Nutzerdaten, Aktivitäten und Profile werden in `data/bot_database.db` gespeichert. Diese Datei ist dein "Gedächtnis".
*   **Backup:** Sichere einfach regelmäßig die Datei `data/bot_database.db`.
*   **Prozess-Kontrolle:** Starte und stoppe die Bots ausschließlich über das Web-Dashboard.

---

**Wichtiger Hinweis:** Wenn du das System auf einem NAS (z.B. Synology oder QNAP) im Docker-Container betreibst, stelle sicher, dass der Ordner `data/` als **Volume** gemountet ist, damit deine Datenbank bei einem Container-Update nicht gelöscht wird.
