# To-Do: Filler- und Fehleranalyse (verbesserte Schritte)

Ziel: Die Doku in `README.md` und `docs/README.md` sprachlich neutral, konsistent und überprüfbar machen.

## Vorgehen (Reihenfolge)



---

## 1) Filler / unnötig werbliche Formulierungen

### Priorität: Hoch



**Definition of Done:** Keine Marketing-Superlative ohne technische Begründung; Aussagen sind konkret und überprüfbar.

---

## 2) Orthografie- und Grammatikfehler

### Priorität: Hoch



**Definition of Done:** Keine offensichtlichen Rechtschreibfehler mehr; Begriffe konsistent im gesamten Doku-Bereich.

---

## 3) Stil- und Konsistenzprobleme

### Priorität: Mittel



**Definition of Done:** Terminologie-Liste erstellt und in beiden README-Dateien konsistent angewendet.

---

## 4) Inhaltliche Schärfung

### Priorität: Hoch


  - Development: `python3 web_dashboard/app.py`
  - Produktion: `gunicorn --bind 0.0.0.0:9002 web_dashboard.app:app`

**Definition of Done:** Jeder Feature-Claim ist im Code oder in der Konfiguration nachvollziehbar; Installationsanweisungen sind widerspruchsfrei.

---

## Optional: Schnell-Checkliste für den finalen Review


---

## 5) Zusätzliche Projektfehler (neu gefunden)

### Priorität: Hoch


  - **Aktion:** Fehlerursache reproduzierbar testen und Regressionstest für Template-Rendering ergänzen.

### Priorität: Mittel


  - **Aktion:** Logging-Artefakte in `.gitignore` aufnehmen und bestehende Logdateien aus der Versionskontrolle entfernen.

**Definition of Done:** Alle neu gefundenen Punkte sind entweder technisch behoben oder bewusst dokumentiert (mit Begründung), und die Doku enthält nur ausführbare/verifizierte Schritte.
