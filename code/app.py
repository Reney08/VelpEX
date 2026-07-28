import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import sqlite3
import logging
import traceback
import webview
from threading import Thread
from io import BytesIO
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

APP_DIR = os.path.dirname(os.path.abspath(__file__))

def get_template_path():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return APP_DIR

def get_db_path():
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = APP_DIR
    return os.path.join(application_path, 'turniere.db')

DB_NAME = get_db_path()
base_dir = get_template_path()
app = Flask(__name__, template_folder=os.path.join(base_dir, 'templates'))
app.secret_key = 'golf_app_secret_key_exe'

@app.errorhandler(Exception)
def handle_exception(e):
    tb = traceback.format_exc()
    try:
        log_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else APP_DIR, 'error_log.txt')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n--- FEHLER BEI {request.path} ---\n{tb}\n")
    except Exception:
        pass
    return f"<div style='padding:20px; font-family:sans-serif;'><h2>Ein Fehler ist aufgetreten:</h2><pre style='background:#f8f9fa; padding:15px; border-radius:5px;'>{tb}</pre></div>", 500

DEFAULT_PUNKTE = {
    '18_loch': {1: 500, 2: 300, 3: 190, 4: 135, 5: 110, 6: 100, 7: 90, 8: 85, 9: 80, 10: 75, 11: 70, 12: 65, 13: 60, 14: 57, 15: 55, 16: 53, 17: 51, 18: 49, 19: 47, 20: 45},
    '9_loch': {1: 250, 2: 150, 3: 95, 4: 67.5, 5: 55, 6: 50, 7: 45, 8: 42.5, 9: 40, 10: 37.5, 11: 35, 12: 32.5, 13: 30, 14: 28.5, 15: 27.5, 16: 26.5, 17: 25.5, 18: 24.5, 19: 23.5, 20: 22.5},
    'clubmeisterschaft': {1: 600, 2: 330, 3: 210, 4: 150, 5: 120, 6: 110, 7: 100, 8: 94, 9: 88, 10: 82, 11: 77, 12: 72, 13: 68, 14: 64, 15: 61, 16: 59, 17: 57, 18: 55, 19: 53, 20: 51},
    'finale': {1: 2000, 2: 1200, 3: 760, 4: 540, 5: 440, 6: 400, 7: 360, 8: 340, 9: 320, 10: 300, 11: 280, 12: 260, 13: 240, 14: 228, 15: 220, 16: 212, 17: 204, 18: 196, 19: 188, 20: 180}
}

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ERMÖGLICHT GLEICHZEITIGE ZUGRIFFE (WAL-Modus)
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=10000;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_metadata (
            table_name TEXT PRIMARY KEY,
            display_name TEXT,
            tournament_type TEXT,
            folder_id INTEGER
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS points_config (
            tournament_type TEXT,
            rank INTEGER,
            points REAL,
            PRIMARY KEY (tournament_type, rank)
        );
    """)
    
    cursor.execute("SELECT COUNT(*) FROM points_config")
    if cursor.fetchone()[0] == 0:
        for t_type, ranks in DEFAULT_PUNKTE.items():
            for r, p in ranks.items():
                cursor.execute("INSERT INTO points_config (tournament_type, rank, points) VALUES (?, ?, ?)", (t_type, r, p))
                
    cursor.execute("PRAGMA table_info(tournament_metadata)")
    cols = [column['name'] for column in cursor.fetchall()]
    if 'folder_id' not in cols:
        cursor.execute("ALTER TABLE tournament_metadata ADD COLUMN folder_id INTEGER;")
        
    conn.commit()
    conn.close()

def get_points_sets():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tournament_type, rank, points FROM points_config")
    rows = cursor.fetchall()
    conn.close()
    
    points_sets = {}
    for row in rows:
        t_type, rank, pts = row['tournament_type'], row['rank'], row['points']
        if t_type not in points_sets:
            points_sets[t_type] = {}
        points_sets[t_type][rank] = int(pts) if pts.is_integer() else pts
    return points_sets

def get_all_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'turnier_%';")
    actual_tables = [row['name'] for row in cursor.fetchall()]
    
    for table in actual_tables:
        cursor.execute("SELECT 1 FROM tournament_metadata WHERE table_name = ?", (table,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO tournament_metadata (table_name, display_name, tournament_type, folder_id) VALUES (?, ?, ?, NULL)", (table, table, '18_loch'))
    conn.commit()
    
    cursor.execute("SELECT table_name, display_name, tournament_type, folder_id FROM tournament_metadata")
    tables = [dict(row) for row in cursor.fetchall() if row['table_name'] in actual_tables]
    conn.close()
    return tables

def get_subfolder_ids(folder_id):
    if folder_id is None:
        return set()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, parent_id FROM folders")
    all_folders = cursor.fetchall()
    conn.close()
    
    result = {int(folder_id)}
    changed = True
    while changed:
        changed = False
        for f in all_folders:
            if f['parent_id'] in result and f['id'] not in result:
                result.add(f['id'])
                changed = True
    return result

@app.context_processor
def inject_sidebar_tree():
    tables = get_all_tables()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM folders ORDER BY name ASC")
    all_folders = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    folder_map = {f['id']: {**f, 'subfolders': [], 'tournaments': []} for f in all_folders}
    root_folders = []
    
    for f in folder_map.values():
        p_id = f['parent_id']
        if p_id and p_id in folder_map:
            folder_map[p_id]['subfolders'].append(f)
        else:
            root_folders.append(f)
            
    unassigned_tournaments = []
    for t in tables:
        f_id = t.get('folder_id')
        if f_id and f_id in folder_map:
            folder_map[f_id]['tournaments'].append(t)
        else:
            unassigned_tournaments.append(t)
            
    return dict(
        folder_tree=root_folders,
        unassigned_tournaments=unassigned_tournaments,
        all_folders_flat=all_folders,
        tables=tables
    )

@app.route('/folder/create', methods=['POST'])
def create_folder():
    name = request.form.get('folder_name', '').strip()
    parent_id = request.form.get('parent_id')
    
    if name:
        parent_id = int(parent_id) if parent_id and parent_id.isdigit() else None
        conn = get_db_connection()
        conn.cursor().execute("INSERT INTO folders (name, parent_id) VALUES (?, ?)", (name, parent_id))
        conn.commit()
        conn.close()
    return redirect(request.referrer or url_for('index'))

@app.route('/folder/delete/<int:folder_id>', methods=['POST'])
def delete_folder(folder_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tournament_metadata SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
    cursor.execute("SELECT parent_id FROM folders WHERE id = ?", (folder_id,))
    res = cursor.fetchone()
    p_id = res['parent_id'] if res else None
    cursor.execute("UPDATE folders SET parent_id = ? WHERE parent_id = ?", (p_id, folder_id))
    cursor.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/tournament/move/<table_name>', methods=['POST'])
def move_tournament(table_name):
    folder_id = request.form.get('folder_id')
    folder_id = int(folder_id) if folder_id and folder_id.isdigit() else None
    
    conn = get_db_connection()
    conn.cursor().execute("UPDATE tournament_metadata SET folder_id = ? WHERE table_name = ?", (folder_id, table_name))
    conn.commit()
    conn.close()
    return redirect(url_for('view_table', table_name=table_name))

def get_overall_data(folder_id):
    if folder_id is None:
        return []
        
    tables = get_all_tables()
    points_sets = get_points_sets()
    
    allowed_folder_ids = get_subfolder_ids(folder_id)
    tables = [t for t in tables if t.get('folder_id') in allowed_folder_ids]
        
    all_points = {}
    tournament_counts = {}
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for t in tables:
        table_name = t['table_name']
        t_type = t['tournament_type']
        points_map = points_sets.get(t_type, points_sets.get('18_loch', {}))
        
        try:
            # Schnelle SQLite Abfrage statt Panda-Verarbeitung
            query = f"SELECT Name, Heimatclub, Rng FROM [{table_name}] WHERE TRIM(Heimatclub) = 'Habichtswald, GC'"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            seen_names = set()
            for row in rows:
                name = row['Name']
                club = row['Heimatclub'] if row['Heimatclub'] else "Kein Club"
                rng_raw = row['Rng']
                
                if name and name not in seen_names:
                    seen_names.add(name)
                    tournament_counts[name] = tournament_counts.get(name, 0) + 1
                
                try:
                    rng_val = int(float(rng_raw))
                    punkte = points_map.get(rng_val, 0)
                except (ValueError, TypeError):
                    punkte = 0
                
                key = (name, club)
                all_points[key] = all_points.get(key, 0) + punkte
                    
        except Exception:
            pass
            
    conn.close()
    
    leaderboard = []
    for (name, club), punkte in all_points.items():
        leaderboard.append({
            'Name': name,
            'Heimatclub': club,
            'Punkte': punkte,
            'Turniere': tournament_counts.get(name, 0)
        })
        
    leaderboard.sort(key=lambda x: (-x['Punkte'], x['Name']))
    return leaderboard

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return "Keine Datei hochgeladen", 400
    file = request.files['file']
    t_type = request.form.get('tournament_type', '18_loch')
    folder_id = request.form.get('folder_id')
    folder_id = int(folder_id) if folder_id and folder_id.isdigit() else None
    
    if file.filename == '' or not file.filename.endswith('.csv'): return "Ungültiges Format", 400
    
    filename = secure_filename(file.filename)
    table_name = "turnier_" + filename.replace('.', '_').lower()
    
    try:
        df = pd.read_csv(file, sep=';')
        df.columns = df.columns.str.strip()
        
        conn = get_db_connection()
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        display_name = filename
        if 'Tournament name' in df.columns and not df.empty:
            display_name = str(df['Tournament name'].iloc[0])
            
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tournament_metadata (table_name, display_name, tournament_type, folder_id)
            VALUES (?, ?, ?, ?)
        """, (table_name, display_name, t_type, folder_id))
        
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
    query = f"SELECT * FROM [{table_name}] WHERE TRIM(Heimatclub) = 'Habichtswald, GC'"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    t_type = current_tournament['tournament_type']
    points_sets = get_points_sets()
    points_map = points_sets.get(t_type, {})
    
    if 'Rng' in df.columns:
        df['Rng_num'] = pd.to_numeric(df['Rng'], errors='coerce')
        df['Punkte'] = df['Rng_num'].apply(lambda x: points_map.get(x, 0) if pd.notna(x) else 0)
        df = df.drop(columns=['Rng_num'])
    
    return render_template(
        'view.html', 
        columns=df.columns.tolist(), 
        rows=df.values.tolist(), 
        current_table=table_name, 
        current_tournament=current_tournament
    )

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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM folders WHERE parent_id IS NULL ORDER BY name DESC")
    year_folders = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    selected_folder_id = request.args.get('folder_id')
    if selected_folder_id and selected_folder_id.isdigit():
        selected_folder_id = int(selected_folder_id)
    elif year_folders:
        selected_folder_id = year_folders[0]['id']
    else:
        selected_folder_id = None
    
    leaderboard = get_overall_data(selected_folder_id) if selected_folder_id else []
    
    return render_template(
        'overall.html', 
        leaderboard=leaderboard, 
        current_table='overall', 
        selected_folder_id=selected_folder_id,
        year_folders=year_folders
    )

@app.route('/overall/pdf')
def download_pdf():
    selected_folder_id = request.args.get('folder_id')
    if selected_folder_id and selected_folder_id.isdigit():
        selected_folder_id = int(selected_folder_id)
    else:
        conn = get_db_connection()
        res = conn.execute("SELECT id FROM folders WHERE parent_id IS NULL ORDER BY name DESC LIMIT 1").fetchone()
        selected_folder_id = res['id'] if res else None
        conn.close()
    
    leaderboard = get_overall_data(selected_folder_id)
    
    folder_title = "Saison"
    if selected_folder_id:
        conn = get_db_connection()
        res = conn.execute("SELECT name FROM folders WHERE id = ?", (selected_folder_id,)).fetchone()
        if res: folder_title = res['name']
        conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#1b4332'), spaceAfter=15)
    
    story.append(Paragraph(f"⛳ Gesamtsiegerliste - {folder_title}", title_style))
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
    return send_file(buffer, as_attachment=True, download_name=f'Gesamtsiegerliste_{folder_title}.pdf', mimetype='application/pdf')

@app.route('/points', methods=['GET'])
def edit_points():
    points_sets = get_points_sets()
    return render_template('points.html', points_sets=points_sets)

@app.route('/points/save', methods=['POST'])
def save_points():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    types = ['18_loch', '9_loch', 'clubmeisterschaft', 'finale']
    for t_type in types:
        for rank in range(1, 21):
            field = f"pts_{t_type}_{rank}"
            val = request.form.get(field)
            if val is not None and val.strip() != '':
                try:
                    p_val = float(val)
                    cursor.execute("INSERT OR REPLACE INTO points_config (tournament_type, rank, points) VALUES (?, ?, ?)", (t_type, rank, p_val))
                except ValueError:
                    pass
    conn.commit()
    conn.close()
    return redirect(url_for('edit_points'))

@app.route('/database/export')
def export_db():
    db_path = get_db_path()
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True, download_name='turniere_backup.db')
    return "Keine Datenbank vorhanden", 404

@app.route('/database/import', methods=['POST'])
def import_db():
    if 'db_file' not in request.files: return "Keine Datei", 400
    file = request.files['db_file']
    if file.filename == '' or not file.filename.endswith('.db'): return "Nur .db Dateien gestattet", 400
    
    file.save(get_db_path())
    return redirect(url_for('index'))

def start_flask():
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Initialisiere Datenbank genau ein Mal beim Start!
    init_db()
    
    flask_thread = Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    try:
        window = webview.create_window(
            "GCH Auswertung Intern", 
            "http://127.0.0.1:5000", 
            width=1300, 
            height=850,
            resizable=True
        )
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open("http://127.0.0.1:5000")
        while True:
            pass