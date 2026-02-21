# To-Do: Filler- und Fehleranalyse (verbesserte Schritte)

Ziel: Die Doku in `README.md` und `docs/README.md` sprachlich neutral, konsistent und überprüfbar machen.

## Vorgehen (Reihenfolge)

- [ ] **Schritt 1 – Tonalität festlegen:** Entscheiden, ob die Dokumentation primär sachlich-technisch oder leicht werblich sein soll.
- [ ] **Schritt 2 – Filler bereinigen:** Werbliche/unscharfe Formulierungen durch neutrale, konkrete Aussagen ersetzen.
- [ ] **Schritt 3 – Sprache korrigieren:** Rechtschreibung, Grammatik und Begriffe vereinheitlichen.
- [ ] **Schritt 4 – Inhalte verifizieren:** Feature-Claims gegen den tatsächlichen Stand prüfen.
- [ ] **Schritt 5 – Struktur verbessern:** Changelog ergänzen und Installationspfade klar trennen.

---

## 1) Filler / unnötig werbliche Formulierungen

### Priorität: Hoch

- [ ] `README.md`: "ultimaten Telegram-Bot-Verwaltungssystem" ersetzen durch "zentrales Telegram-Bot-Verwaltungssystem".
- [ ] `README.md`: Vergleich "wie bei einem professionellen Router" entfernen oder technisch präzisieren.
- [ ] `README.md`: "Keine komplizierte Konfiguration ... nötig" umformulieren zu "Die Konfiguration erfolgt über einen Assistenten".
- [ ] `docs/README.md`: Adjektiv "leistungsstarke" beim NexusMod-Bot nur behalten, wenn messbar begründet; sonst streichen.
- [ ] `docs/README.md`: Schlussformel "maximale Kontrolle und Transparenz" entweder als Vision markieren oder in neutralen Satz überführen.

**Definition of Done:** Keine Marketing-Superlative ohne technische Begründung; Aussagen sind konkret und überprüfbar.

---

## 2) Orthografie- und Grammatikfehler

### Priorität: Hoch

- [ ] `README.md`: "Klane das Repository" → "Klone das Repository".
- [ ] `README.md`: "Firmware-Updates" auf inhaltliche Korrektheit prüfen; ggf. "System-Updates" verwenden.
- [ ] `docs/README.md`: "Telegramm-Bot" konsistent auf "Telegram-Bot" ändern (falls kein bewusstes Wording).

**Definition of Done:** Keine offensichtlichen Rechtschreibfehler mehr; Begriffe konsistent im gesamten Doku-Bereich.

---

## 3) Stil- und Konsistenzprobleme

### Priorität: Mittel

- [ ] Einheitliche Sprachstrategie festlegen: entweder deutsch geprägt (z. B. "Einrichtungsassistent") oder bewusster Anglizismus-Mix.
- [ ] Schreibweise zusammengesetzter Begriffe vereinheitlichen (z. B. "Outfit-Wettbewerb-Dashboard").
- [ ] Produktnaming standardisieren: entweder "NexusMod (ID-Finder)" oder "NexusMod Bot (ehemals ID-Finder Bot)" durchgängig verwenden.

**Definition of Done:** Terminologie-Liste erstellt und in beiden README-Dateien konsistent angewendet.

---

## 4) Inhaltliche Schärfung

### Priorität: Hoch

- [ ] Claims mit Implementierung abgleichen (z. B. "automatischer Bann bei Limit-Erreichung", "Critical Errors in Echtzeit").
- [ ] Für unbestätigte Features Formulierungen abschwächen (z. B. "unterstützt" statt "garantiert").
- [ ] Versionierte Changelog-Sektion hinzufügen, damit "Aktuelles Update" nachvollziehbar ist.
- [ ] Installationswege klar trennen und verlinken:
  - Development: `python3 web_dashboard/app.py`
  - Produktion: `gunicorn --bind 0.0.0.0:9002 web_dashboard.app:app`

**Definition of Done:** Jeder Feature-Claim ist im Code oder in der Konfiguration nachvollziehbar; Installationsanweisungen sind widerspruchsfrei.

---

## Optional: Schnell-Checkliste für den finalen Review

- [ ] Keine Superlative ohne Nachweis
- [ ] Keine Tippfehler
- [ ] Einheitliche Benennungen
- [ ] Nachvollziehbare Feature-Aussagen
- [ ] Klare Trennung Dev/Prod

---

## 5) Zusätzliche Projektfehler (neu gefunden)

### Priorität: Hoch

- [ ] **Installationsdoku verweist auf nicht vorhandenes Skript:** In `docs/INSTALL.md` wird `./devserver.sh` als Startkommando genannt, die Datei existiert im Repository jedoch nicht.
  - **Aktion:** Entweder `devserver.sh` bereitstellen oder die Anleitung auf ein existierendes Startkommando umstellen (z. B. `python3 web_dashboard/app.py`).
- [ ] **Schema-Migration fehlt für bestehende SQLite-Datenbanken:** Der Code nutzt `activities.is_deleted`, in den Logs tritt jedoch `sqlite3.OperationalError: no such column: activities.is_deleted` auf.
  - **Aktion:** Migrationspfad ergänzen (ALTER TABLE oder Alembic-Migration) und beim Start sicher ausführen.
- [ ] **Live-Moderation erzeugt Laufzeitfehler laut Fehlerlog:** In den Critical-Logs ist ein Template-Renderfehler auf `/live_moderation [GET]` dokumentiert.
  - **Aktion:** Fehlerursache reproduzierbar testen und Regressionstest für Template-Rendering ergänzen.

### Priorität: Mittel

- [ ] **Repository enthält auffällige Artefakt-Dateien ohne Zweck:** `bots/id_finder_bot/PY` und `bots/id_finder_bot/import` sind leere Dateien mit unklarem Nutzen.
  - **Aktion:** Zweck klären; falls ohne Funktion, entfernen oder dokumentieren.
- [ ] **Produktions-/Laufzeitlogs werden im Repository geführt:** `app.log.*` und `web_dashboard/critical_errors.log.*` liegen versioniert im Projekt.
  - **Aktion:** Logging-Artefakte in `.gitignore` aufnehmen und bestehende Logdateien aus der Versionskontrolle entfernen.

**Definition of Done:** Alle neu gefundenen Punkte sind entweder technisch behoben oder bewusst dokumentiert (mit Begründung), und die Doku enthält nur ausführbare/verifizierte Schritte.
