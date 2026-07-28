import os
import sqlite3
import sys
import webview
from threading import Thread
from io import BytesIO
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def get_template_path():
    """Findet den temporären Ordner für die HTML-Templates, wenn es eine .exe ist."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.abspath(".")

def get_db_path():
    """Sucht die Datenbank IMMER genau in dem Ordner, wo die .exe (oder app.py) liegt."""
    if getattr(sys, 'frozen', False):
        # Wir sind in der kompilierten .exe
        application_path = os.path.dirname(sys.executable)
    else:
        # Wir sind im normalen Python-Skript
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(application_path, 'turniere.db')

DB_NAME = get_db_path()
base_dir = get_template_path()
app = Flask(__name__, template_folder=os.path.join(base_dir, 'templates'))

# ==========================================================
# 🚀 FUTURE-PROOFING: HIER KANNST DU DIE PUNKTE JEDERZEIT ÄNDERN!
# ==========================================================
PUNKTE_SETS = {
    '18_loch': {
        1: 500, 2: 300, 3: 190, 4: 135, 5: 110,
        6: 100, 7: 90, 8: 85, 9: 80, 10: 75,
        11: 70, 12: 65, 13: 60, 14: 57, 15: 55,
        16: 53, 17: 51, 18: 49, 19: 47, 20: 45
    },
    '9_loch': {
        1: 250, 2: 150, 3: 95, 4: 67.5 , 5: 55,
        6: 50, 7: 45, 8: 42.5, 9: 40, 10: 37.5,
        11: 35, 12: 32.5, 13: 30, 14: 28.5, 15: 27.5,
        16: 26.5, 17: 25.5, 18: 24.5, 19: 23.5, 20: 22.5
    },
    'clubmeisterschaft': {
        1: 600, 2: 330, 3: 210, 4: 150, 5: 120,
        6: 110, 7: 100, 8: 94, 9: 88, 10: 82,
        11: 77, 12: 72, 13: 68, 14: 64, 15: 61,
        16: 59, 17: 57, 18: 55, 19: 53, 20: 51
    },
    'finale': {
        1: 2000, 2: 1200, 3: 760, 4: 540, 5: 440,
        6: 400, 7: 360, 8: 340, 9: 320, 10: 300,
        11: 280, 12: 260, 13: 240, 14: 228, 15: 220,
        16: 212, 17: 204, 18: 196, 19: 188, 20: 180
    }
}

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Erstellt die Metadaten-Tabelle, falls sie noch nicht existiert."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_metadata (
            table_name TEXT PRIMARY KEY,
            display_name TEXT,
            tournament_type TEXT
        );
    """)
    conn.commit()
    conn.close()

def get_all_tables():
    """Gibt alle Turniere inklusive ihrer Metadaten (Anzeigename, Typ) zurück."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Alle physischen Tabellen finden
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'turnier_%';")
    actual_tables = [row['name'] for row in cursor.fetchall()]
    
    # Synchronisation für ältere Tabellen (Abwärtskompatibilität)
    for table in actual_tables:
        cursor.execute("SELECT 1 FROM tournament_metadata WHERE table_name = ?", (table,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO tournament_metadata (table_name, display_name, tournament_type) VALUES (?, ?, ?)", (table, table, '18_loch'))
    conn.commit()
    
    cursor.execute("SELECT table_name, display_name, tournament_type FROM tournament_metadata")
    tables = [dict(row) for row in cursor.fetchall()]
    
    # Nur Tabellen zurückgeben, die auch wirklich physisch existieren
    tables = [t for t in tables if t['table_name'] in actual_tables]
    conn.close()
    return tables

def get_overall_data():
    """Berechnet die Gesamtsiegerliste basierend auf dem gewählten Turniertyp (nur Habichtswald, GC)."""
    tables = get_all_tables()
    all_points = {}
    tournament_counts = {}
    
    conn = get_db_connection()
    for t in tables:
        table_name = t['table_name']
        t_type = t['tournament_type']
        
        # Wähle das passende Punkteset aus der Konfiguration oben
        points_map = PUNKTE_SETS.get(t_type, PUNKTE_SETS['18_loch'])
        
        try:
            # 🚀 HIER NEU: Filtert direkt in der Datenbank nach Heimatclub
            query = f"SELECT Name, Heimatclub, Rng FROM [{table_name}] WHERE TRIM(Heimatclub) = 'Habichtswald, GC'"
            df = pd.read_sql_query(query, conn)
            df.columns = df.columns.str.strip()
            
            if 'Rng' not in df.columns or 'Name' not in df.columns:
                continue
            
            for n in df['Name'].dropna().unique():
                tournament_counts[n] = tournament_counts.get(n, 0) + 1
            
            df['Rng'] = pd.to_numeric(df['Rng'], errors='coerce')
            df = df.dropna(subset=['Name', 'Rng'])
            
            for row in df.itertuples():
                name = row.Name
                club = row.Heimatclub if pd.notna(row.Heimatclub) and str(row.Heimatclub).strip() != 'nan' else "Kein Club"
                rng_val = int(row.Rng)
                
                # Punkte aus dem spezifischen Set holen (Standard: 0 Punkte)
                punkte = points_map.get(rng_val, 0)
                
                # 🚀 HIER NEU: Jeder aus Habichtswald wird aufgenommen, auch mit 0 Punkten
                key = (name, club)
                if key not in all_points:
                    all_points[key] = 0
                all_points[key] += punkte
                    
        except Exception as e:
            print(f"Fehler bei Auswertung von {table_name}: {e}")
            
    conn.close()
    
    leaderboard = []
    for (name, club), punkte in all_points.items():
        leaderboard.append({
            'Name': name,
            'Heimatclub': club,
            'Punkte': punkte,
            'Turniere': tournament_counts.get(name, 0)
        })
        
    df_overall = pd.DataFrame(leaderboard)
    if not df_overall.empty:
        # Sortierung: Erst nach Punkten absteigend, bei Gleichstand nach Name alphabetisch
        df_overall = df_overall.sort_values(by=['Punkte', 'Name'], ascending=[False, True]).reset_index(drop=True)
        return df_overall.to_dict(orient='records')
    return []

@app.route('/')
def index():
    return render_template('index.html', tables=get_all_tables())

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return "Keine Datei hochgeladen", 400
    file = request.files['file']
    t_type = request.form.get('tournament_type', '18_loch') # Holt den ausgewählten Typ (9 oder 18 Loch)
    
    if file.filename == '' or not file.filename.endswith('.csv'): return "Ungültiges Format", 400
    
    filename = secure_filename(file.filename)
    table_name = "turnier_" + filename.replace('.', '_').lower()
    
    try:
        df = pd.read_csv(file, sep=';')
        df.columns = df.columns.str.strip()
        
        conn = get_db_connection()
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Standardmäßiger Anzeigename
        display_name = filename
        if 'Tournament name' in df.columns and not df.empty:
            display_name = str(df['Tournament name'].iloc[0])
            
        # Metadaten in der Tabelle eintragen/ersetzen
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tournament_metadata (table_name, display_name, tournament_type)
            VALUES (?, ?, ?)
        """, (table_name, display_name, t_type))
        
        conn.commit()
        conn.close()
        return redirect(url_for('view_table', table_name=table_name))
    except Exception as e:
        return f"Fehler beim Verarbeiten der CSV: {e}", 500

@app.route('/table/<table_name>')
def view_table(table_name):
    tables = get_all_tables()
    current_tournament = next((t for t in tables if t['table_name'] == table_name), None)
    if not current_tournament: return "Tabelle nicht gefunden", 404
    
    conn = get_db_connection()
    # Nur Habichtswald filtern
    query = f"SELECT * FROM [{table_name}] WHERE TRIM(Heimatclub) = 'Habichtswald, GC'"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 🚀 DYNAMISCHE BEPUNKTUNG FÜR DIE EINZELANSICHT
    t_type = current_tournament['tournament_type']
    points_map = PUNKTE_SETS.get(t_type, PUNKTE_SETS['18_loch'])
    
    # Checken, ob es die Spalte 'Rng' gibt, um Punkte zuzuordnen
    if 'Rng' in df.columns:
        # Ränge in Zahlen umwandeln (falls da z.B. mal "T1" steht)
        df['Rng_num'] = pd.to_numeric(df['Rng'], errors='coerce')
        # Neue Spalte 'Punkte' dynamisch anhand des Dictionaries berechnen (Rest bekommt 0)
        df['Punkte'] = df['Rng_num'].apply(lambda x: points_map.get(x, 0) if pd.notna(x) else 0)
        # Hilfsspalte wieder entfernen
        df = df.drop(columns=['Rng_num'])
    
    return render_template(
        'view.html', 
        tables=tables, 
        columns=df.columns.tolist(), 
        rows=df.values.tolist(), 
        current_table=table_name, 
        display_name=current_tournament['display_name'],
        tournament_type=current_tournament['tournament_type']
    )

@app.route('/rename/<table_name>', methods=['POST'])
def rename_tournament(table_name):
    """Ändert den Anzeigenamen des Turniers in den Metadaten."""
    new_name = request.form.get('display_name', '').strip()
    if new_name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE tournament_metadata SET display_name = ? WHERE table_name = ?", (new_name, table_name))
        conn.commit()
        conn.close()
    return redirect(url_for('view_table', table_name=table_name))

@app.route('/delete/<table_name>', methods=['POST'])
def delete_table(table_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
        cursor.execute("DELETE FROM tournament_metadata WHERE table_name = ?", (table_name,))
        conn.commit()
    except Exception as e:
        return f"Fehler beim Löschen: {e}", 500
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/overall')
def overall_leaderboard():
    return render_template('overall.html', tables=get_all_tables(), leaderboard=get_overall_data(), current_table='overall')

@app.route('/overall/pdf')
def download_pdf():
    leaderboard = get_overall_data()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, leading=26, textColor=colors.HexColor('#1b4332'), spaceAfter=15)
    
    story.append(Paragraph("⛳ Gesamtsiegerliste - Turnierserie", title_style))
    story.append(Spacer(1, 10))
    
    table_data = [['Pos.', 'Name', 'Heimatclub', 'Turniere', 'Punkte']]
    for idx, row in enumerate(leaderboard, 1):
        table_data.append([str(idx), row['Name'], row['Heimatclub'], str(row['Turniere']), str(row['Punkte'])])
        
    t = Table(table_data, colWidths=[40, 160, 160, 75, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#212529')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (3,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 11),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dee2e6')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 10),
    ]))
    
    story.append(t)
    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='Gesamtsiegerliste.pdf', mimetype='application/pdf')



def start_flask():
    """Startet den Flask-Server im Hintergrund."""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    
if __name__ == '__main__':
    # Prüfen, ob wir auf Windows sind ODER das Programm bereits als EXE läuft
    if sys.platform == 'win32' or getattr(sys, 'frozen', False):
        # 💻 WINDOWS / EXE MODUS: Als echtes Desktop-Fenster anzeigen
        flask_thread = Thread(target=start_flask)
        flask_thread.daemon = True
        flask_thread.start()
        
        webview.create_window("GCH Auswertung Intern", "http://127.0.0.1:5000", width=1200, height=800)
        webview.start()
    else:
        # 🐧 LINUX ENTWICKLUNGSMODUS: Normal im Browser starten
        import webbrowser
        from threading import Timer
        
        def open_browser():
            webbrowser.open_new("http://127.0.0.1:5000/")
            
        # Öffnet nach 1.5 Sekunden automatisch deinen Linux-Browser
        Timer(1.5, open_browser).start()
        
        print("-> Entwicklungsmodus auf Linux: App startet im normalen Browser!")
        app.run(host='127.0.0.1', port=5000, debug=True)
