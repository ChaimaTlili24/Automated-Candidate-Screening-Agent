from flask import Flask, render_template, request, g, abort, redirect, url_for
from werkzeug.utils import secure_filename
import os
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image
from docx import Document
import re
from pymongo import MongoClient
from flask import get_flashed_messages, flash

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# MongoDB
mongo_client = MongoClient("mongodb://localhost:27017/")
db_mongo = mongo_client["cv_database"]
collection_cv = db_mongo["candidates"]

import sqlite3

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = "chaima_tlili_cv_flash_123456"

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
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except Exception:
        try:
            images = convert_from_path(pdf_path)
            for img in images:
                text += pytesseract.image_to_string(img, lang='eng')
        except:
            pass
    return text


def extract_text_from_docx(docx_path):
    text = ""
    try:
        doc = Document(docx_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except:
        pass
    return text


def extract_info(cv_path):
    ext = cv_path.lower()

    if ext.endswith((".jpg", ".png", ".jpeg")):
        img = Image.open(cv_path)
        text = pytesseract.image_to_string(img)

    elif ext.endswith(".pdf"):
        text = extract_text_from_pdf(cv_path)

    elif ext.endswith(".docx"):
        text = extract_text_from_docx(cv_path)

    else:
        return None

    # Nettoyage
    text_clean = text.replace("\x0c", "\n").strip()
    lines = [l.strip() for l in text_clean.split("\n") if l.strip()]

    # Nom = première ligne non vide
    name = lines[0] if lines else ""

    # Email
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails = re.findall(email_pattern, text_clean)
    email = emails[0] if emails else ""

    # Skills
    skills = []
    capture = False
    for line in lines:
        if "skill" in line.lower():
            capture = True
            continue
        if capture:
            if any(k in line.lower() for k in ["experience", "education", "projects"]):
                break
            skills.append(line)

    return {
        "name": name,
        "email": email,
        "skills": skills
    }
@app.route("/upload_cv", methods=["POST"])
def upload_cv():
    file = request.files.get("cv_file")

    if not file:
        return "Aucun fichier reçu"

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # Extraction
    extracted = extract_info(file_path)

    return render_template("cv_form.html", extracted=extracted)
@app.route("/save_cv", methods=["POST"])
def save_cv():
    name = request.form.get("name")
    email = request.form.get("email")
    skills = request.form.get("skills").split(",")

    document = {
        "name": name,
        "email": email,
        "skills": skills
    }

    collection_cv.insert_one(document)

    # Message flash
    flash("✅ Vos informations ont bien été sauvegardées !")

    return redirect(url_for("index"))

if __name__ == '__main__':
    app.run(debug=True)
