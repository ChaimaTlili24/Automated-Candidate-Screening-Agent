from flask import Flask, render_template, request, g, abort
import sqlite3

app = Flask(__name__)
DATABASE = 'jobs.db'

# Couleurs pour chaque domaine
DOMAIN_COLORS = {
    "Data": "#1f77b4",
    "Software": "#ff7f0e",
    "Fullstack": "#2ca02c",
    "Mobile": "#d62728",
    "Devops": "#9467bd",
    "AI": "#8c564b",
    "Other": "#7f7f7f",
    "Backend": "#17becf"
}

# Tous les domaines disponibles (même si aucun job n'existe)
ALL_DOMAINS = ["Data", "Software", "Fullstack", "Mobile", "Devops", "AI", "Other", "Backend"]

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

def get_all_jobs(search='', domain='', offset=0, limit=12):
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
    # retourne tous les domaines possibles
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
    per_page = 12

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

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    job = get_job_by_id(job_id)
    if not job:
        abort(404)
    return render_template('job_detail.html', job=job, domain_colors=DOMAIN_COLORS)

if __name__ == '__main__':
    app.run(debug=True)
