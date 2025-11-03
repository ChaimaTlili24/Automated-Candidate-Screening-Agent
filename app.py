from flask import Flask, render_template, request, g, abort
import sqlite3

app = Flask(__name__)
DATABASE = r"C:\Users\ROYAUME MEDIAS\OneDrive\Desktop\Similarity\jobs.db"

# Couleurs pour chaque domaine
# Couleurs pour chaque domaine
DOMAIN_COLORS = {
    "AI": "#1f77b4",             # bleu
    "Data": "#2ca02c",           # vert
    "Backend": "#ff7f0e",        # orange
    "Frontend": "#9467bd",       # violet
    "Fullstack": "#17becf",      # cyan
    "Mobile": "#d62728",         # rouge
    "DevOps": "#8c564b",         # brun
    "Cloud": "#e377c2",          # rose
    "Security": "#7f7f7f",       # gris
    "Infrastructure": "#bcbd22", # jaune-vert
    "QA / Testing": "#ff69b4",   # rose vif
    "Management": "#8a2be2",     # violet foncé
    "ERP": "#ffd700",             # or
    "Embedded / IoT": "#32cd32", # vert lime
    "Other": "#000000"            # noir
}

# Tous les domaines disponibles
ALL_DOMAINS = [
    "AI", "Data", "Backend", "Frontend", "Fullstack", "Mobile", "DevOps",
    "Cloud", "Security", "Infrastructure", "QA / Testing", "Management",
    "ERP", "Embedded / IoT", "Other"
]

# ---------- DB Helper ----------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # accéder aux colonnes par nom
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def get_all_jobs(search='', domain='', offset=0, limit=9):
    db = get_db()
    cursor = db.cursor()
    query = "SELECT id, title, description, domain FROM jobs WHERE 1=1"
    params = []
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if domain:
        query += " AND domain = ?"
        params.append(domain)
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)
    return cursor.fetchall()

def count_jobs(search='', domain=''):
    db = get_db()
    cursor = db.cursor()
    query = "SELECT COUNT(*) FROM jobs WHERE 1=1"
    params = []
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if domain:
        query += " AND domain = ?"
        params.append(domain)
    cursor.execute(query, params)
    return cursor.fetchone()[0]

def get_domains():
    return ALL_DOMAINS

def get_job_by_id(job_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return cursor.fetchone()

# ---------- Routes ----------
@app.route('/', methods=['GET'])
def index():
    search = request.args.get('search', '')
    domain = request.args.get('domain', '')
    page = int(request.args.get('page', 1))
    per_page = 9

    total_jobs = count_jobs(search, domain)
    total_pages = (total_jobs + per_page - 1) // per_page
    offset = (page - 1) * per_page

    jobs = get_all_jobs(search, domain, offset=offset, limit=per_page)
    domains = get_domains()

    return render_template(
        'index.html',
        jobs=jobs,
        domains=domains,
        search=search,
        selected_domain=domain,
        domain_colors=DOMAIN_COLORS,
        page=page,
        total_pages=total_pages
    )

import markdown2

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    job = get_job_by_id(job_id)
    if not job:
        abort(404)

    job_title = job['title']
    job_description = job['description']
    job_domain = job['domain']

    # Convertir Markdown en HTML
    job_description_html = markdown2.markdown(job_description)

    return render_template(
        'job_detail.html',
        job_title=job_title,
        job_description_html=job_description_html,  # Bien passer la version HTML
        job_domain=job_domain,
        domain_colors=DOMAIN_COLORS
    )

if __name__ == '__main__':
    app.run(debug=True)
