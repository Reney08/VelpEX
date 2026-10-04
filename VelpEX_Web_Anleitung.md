# VelpEX als Webanwendung importieren und starten

Diese Anleitung zeigt Schritt für Schritt, wie du das Projekt [Reney08/VelpEX](https://github.com/Reney08/VelpEX) herunterlädst und **als Webanwendung im Browser** startest – ohne das Windows-Programmfenster (pywebview).

> **Wichtig:** Starte das Projekt **nicht** mit `python app.py`. Dieser Aufruf öffnet das Windows-Fenster („Golf Turnier Manager“ über Edge WebView2). Für die Webanwendung wird stattdessen der Flask-Server direkt gestartet (siehe Schritt 5).

---

## Überblick: Was ist im Projekt enthalten?

```
VelpEX/
├── requirements.txt      # Python-Abhängigkeiten
├── README.md
├── LICENSE
└── code/
    ├── app.py            # Flask-App (Web) + Startcode für das Windows-Fenster
    ├── templates/        # HTML-Seiten (index, view, overall, points, base)
    ├── habichslogo.jpeg
    └── app_icon.ico
```

Die Webanwendung ist eine **Flask-App** mit **SQLite-Datenbank** (wird beim ersten Start automatisch als `code/turniere.db` angelegt). Turnierergebnisse werden als **CSV-Dateien** hochgeladen und ausgewertet.

---

## Voraussetzungen

| Programm | Version | Prüfen mit |
|---|---|---|
| Python | 3.10 oder neuer (getestet mit 3.13) | `python --version` |
| Git | beliebig aktuell | `git --version` |
| Webbrowser | beliebig (Chrome, Edge, Firefox, Safari) | – |

Python gibt es unter <https://www.python.org/downloads/>. Unter Windows beim Installieren **„Add python.exe to PATH“** ankreuzen.

> Unter Linux/macOS heißt der Befehl oft `python3` statt `python`. Nutze dann überall `python3`.

---

## Schritt 1: Projekt von GitHub importieren (klonen)

Terminal öffnen (Windows: PowerShell oder Eingabeaufforderung) und in den Ordner wechseln, in dem das Projekt liegen soll:

```bash
git clone https://github.com/Reney08/VelpEX.git
cd VelpEX
```

> **Ohne Git:** Auf der GitHub-Seite auf **Code → Download ZIP** klicken, die ZIP-Datei entpacken und im Terminal in den entpackten Ordner `VelpEX` wechseln.

---

## Schritt 2: Virtuelle Umgebung anlegen (empfohlen)

Damit die Pakete nicht mit anderen Python-Projekten kollidieren:

```bash
python -m venv venv
```

**Aktivieren:**

| System | Befehl |
|---|---|
| Windows (PowerShell) | `venv\Scripts\Activate.ps1` |
| Windows (Eingabeaufforderung) | `venv\Scripts\activate.bat` |
| Linux / macOS | `source venv/bin/activate` |

Wenn die Umgebung aktiv ist, steht `(venv)` vor der Eingabezeile.

> **PowerShell meldet „Ausführung von Skripts ist deaktiviert“?** Einmalig ausführen:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> und Schritt 2 wiederholen.

---

## Schritt 3: Abhängigkeiten installieren

Im Projekt-Hauptordner (dort, wo `requirements.txt` liegt):

```bash
pip install -r requirements.txt
```

Das installiert u. a. Flask, pandas und reportlab (PDF-Export).

> **Hinweis zu pywebview:** Das Paket steht ebenfalls in der `requirements.txt` und wird mitinstalliert. Das ist auch für die Webanwendung nötig, weil `app.py` es beim Start importiert. Es wird im Web-Betrieb aber **nicht** benutzt – es öffnet sich kein Fenster.

---

## Schritt 4: In den Code-Ordner wechseln

```bash
cd code
```

Du befindest dich jetzt im Ordner mit `app.py` und `templates/`.

---

## Schritt 5: Webanwendung starten

Ein einziger Befehl (er legt die Datenbank an und startet den Webserver):

```bash
python -c "import app; app.init_db(); app.app.run(host='127.0.0.1', port=5000, debug=False)"
```

Wenn alles klappt, erscheint:

```
 * Serving Flask app 'app'
 * Running on http://127.0.0.1:5000
```

**Warum nicht einfach `flask run`?** Die Datenbanktabellen werden in `app.py` nur im Windows-Startblock (`if __name__ == '__main__':`) angelegt. Mit `flask run` würde die Startseite deshalb mit einem Fehler 500 abbrechen. Der Befehl oben ruft `init_db()` selbst auf.

---

## Schritt 6: Im Browser öffnen

Adresse aufrufen:

**<http://127.0.0.1:5000>**

Beenden kannst du den Server im Terminal mit **Strg + C**.

---

## Schritt 7: Erste Schritte in der Anwendung

1. **Ordner anlegen:** In der Seitenleiste einen Ordner anlegen, z. B. `2026`. Ordner auf oberster Ebene gelten als Saison/Jahr und erscheinen in der Gesamtwertung. Darunter lassen sich Unterordner anlegen.
2. **CSV hochladen:** Turnierdatei (`.csv`, Trennzeichen **Semikolon `;`**) hochladen, Turnierart wählen (`18_loch`, `9_loch`, `clubmeisterschaft`, `finale`) und den Ordner zuweisen.
3. **Pflichtspalten in der CSV:** `Name`, `Heimatclub` und `Rng` (Rang). Optional `Tournament name` – daraus wird der Anzeigename.
4. **Ergebnisse ansehen:** Es werden nur Spieler mit Heimatclub `Habichtswald, GC` ausgewertet. Die Punkte ergeben sich aus dem Rang und der Turnierart.
5. **Gesamtwertung:** Unter `/overall` gibt es die Gesamtsiegerliste pro Saison-Ordner, als PDF herunterladbar.
6. **Punktetabelle anpassen:** Unter `/points` lassen sich die Punkte pro Platz (1–20) je Turnierart ändern.
7. **Datenbank sichern:** Unter `/database/export` lädt man die Datenbank als `turniere_backup.db` herunter, mit `/database/import` spielt man ein Backup wieder ein.

Beispiel für eine minimale Test-CSV:

```csv
Tournament name;Name;Heimatclub;Rng
Testcup;Max Muster;Habichtswald, GC;1
Testcup;Erika Beispiel;Habichtswald, GC;2
```

---

## Optional: Startskript anlegen

Damit du den langen Befehl nicht jedes Mal eintippen musst, erstelle im Ordner `code/` eine Datei `start_web.py`:

```python
import app

app.init_db()
app.app.run(host="127.0.0.1", port=5000, debug=False)
```

Danach startest du die Webanwendung einfach mit:

```bash
python start_web.py
```

---

## Optional: Im Netzwerk erreichbar machen

Standardmäßig ist die Seite nur auf deinem eigenen Rechner erreichbar. Für den Zugriff von anderen Geräten im selben Netzwerk `host='127.0.0.1'` durch `host='0.0.0.0'` ersetzen und dann `http://<IP-des-Rechners>:5000` aufrufen. Die App hat keine Anmeldung – nutze das nur in einem vertrauenswürdigen Netzwerk.

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| `python` wird nicht gefunden | Unter Windows `py` statt `python` versuchen; sonst Python mit „Add to PATH“ neu installieren. Unter Linux/macOS `python3` nutzen. |
| `ModuleNotFoundError: No module named 'flask'` | Virtuelle Umgebung nicht aktiv (Schritt 2) oder Abhängigkeiten nicht installiert (Schritt 3). |
| Fehler 500 auf der Startseite | Die App wurde ohne `init_db()` gestartet (z. B. mit `flask run`). Startbefehl aus Schritt 5 verwenden. |
| `Address already in use` / Port 5000 belegt | Anderen Port verwenden, z. B. `port=5001`, und `http://127.0.0.1:5001` öffnen. Unter macOS belegt AirPlay-Empfang häufig Port 5000. |
| Fehler beim Installieren von pandas/numpy | Python-Version prüfen (3.10 oder neuer) und `pip install --upgrade pip` ausführen. |
| Es öffnet sich ein Fenster statt des Browsers | Es wurde `python app.py` gestartet (Windows-Variante). Stattdessen Schritt 5 verwenden. |
| Alle Daten weg nach Umzug in anderen Ordner | Die Datenbank liegt als `turniere.db` im Ordner `code/`. Datei mitkopieren oder Backup-Export/-Import nutzen. |

---

## Zusammenfassung (Kurzfassung)

```bash
git clone https://github.com/Reney08/VelpEX.git
cd VelpEX
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd code
python -c "import app; app.init_db(); app.app.run(host='127.0.0.1', port=5000, debug=False)"
```

Danach im Browser: **<http://127.0.0.1:5000>**
