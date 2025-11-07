from flask import Flask, render_template, request, g, abort, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
import os
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image
from docx import Document
import re
import sqlite3
import markdown2

# --------------------------------------
# ✅ CONFIG FLASK
# --------------------------------------
app = Flask(__name__)
app.secret_key = "secret123"   # Sessions + flash

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# --------------------------------------
# ✅ TESSERACT PATH
# --------------------------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --------------------------------------
# ✅ MONGODB (CV + Users)
# --------------------------------------
mongo_client = MongoClient("mongodb://localhost:27017/")
db_mongo = mongo_client["cv_database"]

collection_cv = db_mongo["candidates"]   # CV sauvegardés
users_col = db_mongo["users"]            # Utilisateurs (Candidat + RH)

# --------------------------------------
# ✅ Ajout automatique de 2 RH
# --------------------------------------
def init_rh_users():
    existing_rh = users_col.count_documents({"role": "rh"})
    if existing_rh == 0:
        rh1 = {
            "fullname": "RH Admin 1",
            "email": "rh1@company.com",
            "password": generate_password_hash("1234"),
            "role": "rh"
        }
        rh2 = {
            "fullname": "RH Admin 2",
            "email": "rh2@company.com",
            "password": generate_password_hash("1234"),
            "role": "rh"
        }
        users_col.insert_many([rh1, rh2])
        print("✅ 2 comptes RH créés automatiquement !")

init_rh_users()

# --------------------------------------
# ✅ SQLITE (Jobs)
# --------------------------------------
DATABASE = r"C:\Users\ROYAUME MEDIAS\OneDrive\Desktop\Similarity\jobs.db"

DOMAIN_COLORS = {
    "AI": "#1f77b4",
    "Data": "#2ca02c",
    "Backend": "#ff7f0e",
    "Frontend": "#9467bd",
    "Fullstack": "#17becf",
    "Mobile": "#d62728",
    "DevOps": "#8c564b",
    "Cloud": "#e377c2",
    "Security": "#7f7f7f",
    "Infrastructure": "#bcbd22",
    "QA / Testing": "#ff69b4",
    "Management": "#8a2be2",
    "ERP": "#ffd700",
    "Embedded / IoT": "#32cd32",
    "Other": "#000000"
}

ALL_DOMAINS = list(DOMAIN_COLORS.keys())

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def get_all_jobs(search='', domain='', offset=0, limit=9):
    db = get_db()
    cursor = db.cursor()
    query = "SELECT id, title, description, domain FROM jobs WHERE 1=1"
    params = []

    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    if domain:
        query += " AND domain = ?"
        params.append(domain)

    query += " LIMIT ? OFFSET ?"
    params += [limit, offset]

    cursor.execute(query, params)
    return cursor.fetchall()

def count_jobs(search='', domain=''):
    db = get_db()
    cursor = db.cursor()
    query = "SELECT COUNT(*) FROM jobs WHERE 1=1"
    params = []

    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    if domain:
        query += " AND domain = ?"
        params.append(domain)

    cursor.execute(query, params)
    return cursor.fetchone()[0]

def get_job_by_id(job_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return cursor.fetchone()

# --------------------------------------
# ✅ ROUTE ACCUEIL (Jobs + Recherche)
# --------------------------------------
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

    return render_template(
        "index.html",
        jobs=jobs,
        domains=ALL_DOMAINS,
        search=search,
        selected_domain=domain,
        domain_colors=DOMAIN_COLORS,
        page=page,
        total_pages=total_pages
    )

# --------------------------------------
# ✅ JOB DETAILS
# --------------------------------------
@app.route('/job/<int:job_id>')
def job_detail(job_id):
    job = get_job_by_id(job_id)
    if not job:
        abort(404)

    job_description_html = markdown2.markdown(job["description"])

    return render_template(
        "job_detail.html",
        job_title=job["title"],
        job_description_html=job_description_html,
        job_domain=job["domain"],
        domain_colors=DOMAIN_COLORS
    )

# --------------------------------------
# ✅ EXTRACTION CV
# --------------------------------------
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except:
        try:
            images = convert_from_path(pdf_path)
            for img in images:
                text += pytesseract.image_to_string(img, lang="eng")
        except:
            pass
    return text


def extract_text_from_docx(docx_path):
    try:
        doc = Document(docx_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except:
        return ""


def extract_info(cv_path):
    ext = cv_path.lower()

    if ext.endswith((".jpg", ".jpeg", ".png")):
        text = pytesseract.image_to_string(Image.open(cv_path))

    elif ext.endswith(".pdf"):
        text = extract_text_from_pdf(cv_path)

    elif ext.endswith(".docx"):
        text = extract_text_from_docx(cv_path)

    else:
        return None

    text = text.replace("\x0c", "\n").strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # ✅ On ignore NAME et EMAIL → ils viendront du user connecté
    # ------------------------------------------------------------
    
    # ✅ Extract SKILLS uniquement
    skills = []
    capture = False
    for line in lines:
        if "skill" in line.lower():
            capture = True
            continue
        if capture and any(x in line.lower() for x in ["experience", "education"]):
            break
        if capture:
            skills.append(line)

    return {
        "skills": skills
    }


# ---------------------------------------------------
# ✅ UPLOAD CV + EXTRACTION
# ---------------------------------------------------
@app.route("/upload_cv", methods=["POST"])
def upload_cv():
    file = request.files.get("cv_file")
    if not file:
        return "Aucun fichier reçu"

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    extracted = extract_info(file_path)

    return render_template(
    "cv_form.html",
    name=session.get("user_fullname"),
    email=session.get("user_email"),
    skills=extracted["skills"]
)


# ---------------------------------------------------
# ✅ SAVE CV = name + email from session
# ---------------------------------------------------
@app.route("/save_cv", methods=["POST"])
def save_cv():

    # ✅ Name & Email → depuis user connecté
    name = session.get("user_fullname")
    email = session.get("user_email")

    # ✅ Skills extraites du formulaire
    skills_raw = request.form.get("skills")
    skills = skills_raw.split(",") if skills_raw else []

    document = {
        "name": name,
        "email": email,
        "skills": skills
    }

    collection_cv.insert_one(document)

    flash("✅ Vos informations ont bien été sauvegardées !")
    return redirect(url_for("index"))

# --------------------------------------
# ✅ SIGN UP (CANDIDATS)
# --------------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        password = request.form['password']

        # Vérifier email existant
        if users_col.find_one({"email": email}):
            flash("⚠️ Cet email est déjà utilisé")
            return redirect('/signup')

        # Création du candidat
        user = {
            "fullname": fullname,
            "email": email,
            "password": generate_password_hash(password),
            "role": "candidat"
        }
        users_col.insert_one(user)

        flash("✅ Compte créé avec succès ! Veuillez vous connecter.")
        return redirect('/login')

    return render_template("auth.html", mode="signup")




# --------------------------------------
# ✅ SIGN IN
# --------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get("email")
        password = request.form.get("password")

        # Chercher l'utilisateur dans MongoDB
        user = users_col.find_one({"email": email})

        # Vérification email + mot de passe
        if not user or not check_password_hash(user["password"], password):
            flash("❌ Email ou mot de passe incorrect")
            return redirect('/login')

        # ✅ Stocker infos dans la session
        session["user_email"] = user["email"]
        session["user_fullname"] = user.get("fullname", "")   # ✅ Ajout du fullname
        session["role"] = user["role"]

        # ✅ Redirection selon le role
        if user["role"] == "rh":
            return redirect('/rh/dashboard')   # Affichera rh_dashbord.html

        return redirect('/')  # ✅ Candidat → page index.html

    # ✅ Utiliser le même template auth.html pour login
    return render_template("auth.html", mode="login")



# --------------------------------------
# ✅ DASHBOARD CANDIDAT
# --------------------------------------
@app.route('/candidate/dashboard')
def candidate_dashboard():
    if session.get("role") != "candidat":
        return redirect('/')
    return render_template("candidate_dashboard.html")

# --------------------------------------
# ✅ DASHBOARD RH
# --------------------------------------
@app.route('/rh/dashboard')
def rh_dashboard():
    if session.get("role") != "rh":
        return redirect('/')

    candidats = list(users_col.find({"role": "candidat"}))
    return render_template("rh_dashboard.html", candidats=candidats)

# --------------------------------------
# ✅ LOGOUT
# --------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# --------------------------------------
# ✅ RUN
# --------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
