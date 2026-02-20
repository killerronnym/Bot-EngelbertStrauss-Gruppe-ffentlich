# 🚀 Telegram Bot Ökosystem: All-in-One Dashboard

Willkommen beim ultimaten Telegram-Bot-Verwaltungssystem! Dieses Projekt vereint mehrere spezialisierte Bots unter einer einzigen, modernen Weboberfläche mit Live-Moderation, automatisierten Updates und einem benutzerfreundlichen Installations-Assistenten.

## ✨ Highlights

*   **🛡️ Live-Moderations-Dashboard:** Überwache und moderiere deine Telegram-Gruppen in Echtzeit direkt im Browser. Lösche Nachrichten, verwarne oder banne Nutzer mit nur einem Klick.
*   **📦 Integriertes Update-System:** Erhalte Firmware-Updates wie bei einem professionellen Router. Ein Klick im Dashboard genügt, um das gesamte System auf den neuesten Stand zu bringen.
*   **🪄 Setup-Wizard:** Keine komplizierte Konfiguration von JSON-Dateien nötig. Beim ersten Start führt dich ein Assistent durch die Einrichtung von Admin-Account und Bot-Tokens.
*   **🎮 Vielseitige Bots:**
    *   **NexusMod (ID-Finder):** Das Herzstück für Moderation und System-Identifikation.
    *   **Minecraft Status Pro:** Live-Monitoring deines Game-Servers mit automatischer Nachrichten-Rotation.
    *   **Quiz & Umfrage Bots:** Plane und sende interaktive Inhalte vollautomatisch.
    *   **Outfit-Wettbewerb:** Steuerung von täglichen Community-Duellen.

## 🛠️ Installation & Schnellstart

### Voraussetzungen
*   Python 3.10 oder höher
*   Linux-basiertes System (z.B. NAS/Synology, Ubuntu, Docker)

### Installation
1.  Klane das Repository:
    ```bash
    git clone https://github.com/killerronnym/Bot-EngelbertStrauss-Gruppe-ffentlich.git
    cd Bot-EngelbertStrauss-Gruppe-ffentlich
    ```
2.  Erstelle eine virtuelle Umgebung und installiere die Abhängigkeiten:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
3.  Starte das Web-Dashboard:
    ```bash
    python3 web_dashboard/app.py
    ```

### Ersteinrichtung
Nach dem Start kannst du das Dashboard unter `http://deine-ip:9002` aufrufen. Da noch keine Konfiguration existiert, wirst du automatisch zum **Setup-Wizard** geleitet. Dort legst du deinen Admin-Account fest und hinterlegst deine Bot-Tokens.

## 🛡️ Datenschutz & Sicherheit
Dieses System wurde für maximale Privatsphäre entwickelt:
*   **Persistence:** Updates überschreiben niemals deine lokalen Datenbanken, Quizfragen oder individuellen Bot-Einstellungen.
*   **Local Storage:** Alle Daten verbleiben lokal in deinem `data/` Ordner und werden nicht in die Cloud übertragen.
*   **Access Control:** Das gesamte Dashboard ist durch ein sicheres Passwort-Hashing-Verfahren geschützt.

---
*Entwickelt für maximale Kontrolle und Transparenz in deiner Telegram-Community.*
👤 **Entwickler:** @pup_Rinno_cgn
