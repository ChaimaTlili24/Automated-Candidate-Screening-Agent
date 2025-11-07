from flask import Flask, render_template, request, g, abort, redirect, url_for, session, flash , jsonify
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
from fpdf import FPDF
from datetime import datetime
from matching_utils import run_matching, extract_technical_skills
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
from gpt4all import GPT4All
MODEL_PATH = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
model = GPT4All(MODEL_PATH)

# --------------------------------------
# ✅ MONGODB (CV + Users)
# --------------------------------------
mongo_client = MongoClient("mongodb://localhost:27017/")
db_mongo = mongo_client["cv_database"]

collection_cv = db_mongo["candidates"]   # CV sauvegardés
users_col = db_mongo["users"]     
collection_matching = db_mongo["matching_results"]       # Utilisateurs (Candidat + RH)
# === APRÈS app = Flask(__name__) ===
# === APRÈS app = Flask(__name__) ===
app.db = type('DB', (), {})()
app.db.mongo = db_mongo
app.db.candidates = collection_cv
app.db.matching_results = collection_matching

def get_sqlite_db():
    return get_db()
app.db.get_sqlite_db = get_sqlite_db

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
        job_id=job_id,
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
@app.route("/upload_cv", methods=["GET", "POST"])
def upload_cv():
    email = session.get("user_email")
    fullname = session.get("user_fullname")
    if not email or not fullname:
        return redirect("/login")

    selected_job = None
    message = None
    extracted = {"skills": []}
    cover_letters = []

    # === GET : charger job_id ===
    if request.method == "GET":
        job_id = request.args.get("job_id")
        if job_id:
            job = get_job_by_id(int(job_id))
            if job:
                selected_job = {
                    "id": job["id"],
                    "title": job["title"],
                    "description": job["description"]
                }
                # SAUVEGARDER LE JOB_ID DANS LA SESSION
                session['selected_job_id'] = job_id
                session['selected_job_title'] = job["title"]

    # === POST ===
    if request.method == "POST":
        # RÉCUPÉRER LE JOB_ID DEPUIS LE FORMULAIRE EN PRIORITÉ
        job_id = request.form.get('job_id') or session.get('selected_job_id')
        job_title = request.form.get('job_title') or session.get('selected_job_title', '')
        
        print(f"DEBUG: job_id from form: {request.form.get('job_id')}, from session: {session.get('selected_job_id')}")
        
        # --- UPLOAD CV ---
        if "cv_file" in request.files:
            file = request.files["cv_file"]
            if file and file.filename:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(file_path)

                extracted = extract_info(file_path)
                if extracted:
                    collection_cv.update_one(
                        {"email": email, "type": "cv"},
                        {"$set": {
                            "name": fullname,
                            "email": email,
                            "skills": extracted["skills"],
                            "job_id": job_id,  # SAUVEGARDER LE JOB_ID
                            "job_title": job_title,
                            "updated_at": datetime.now()
                        }},
                        upsert=True
                    )
                    message = "CV analysé avec succès"
                else:
                    message = "Erreur extraction CV"

        # --- SAUVEGARDER TOUT ---
        elif request.form.get("action") == "save_all_data":
            name = request.form.get("name", fullname)
            skills_raw = request.form.get("skills", "")
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

            pending = session.get("pending_cover_letters", [])
            existing = collection_cv.find_one({"email": email, "type": "cv"})
            old_covers = existing.get("cover_letters", []) if existing else []
            
            # AJOUTER LE JOB_ID AUX COVER LETTERS PENDING
            for cover in pending:
                cover["job_id"] = job_id
                cover["job_title"] = job_title
            
            all_covers = old_covers + pending

            # SAUVEGARDER AVEC LE JOB_ID
            collection_cv.update_one(
                {"email": email, "type": "cv"},
                {"$set": {
                    "name": name,
                    "email": email,
                    "skills": skills,
                    "cover_letters": all_covers,
                    "job_id": job_id,  # CORRECTION : SAUVEGARDER LE JOB_ID
                    "job_title": job_title,
                    "updated_at": datetime.now()
                }},
                upsert=True
            )

            session.pop("pending_cover_letters", None)

            flash(f"Vos informations ont été sauvegardées avec succès pour le poste : {job_title} !", "success")
            return redirect(url_for("index"))

    # === CHARGER DONNÉES EXISTANTES ===
    existing = collection_cv.find_one({"email": email, "type": "cv"})
    if existing:
        skills_db = existing.get("skills", [])
        if isinstance(skills_db, str):
            extracted["skills"] = [s.strip() for s in skills_db.split(",") if s.strip()]
        else:
            extracted["skills"] = skills_db
        cover_letters = existing.get("cover_letters", [])
        
        # CHARGER LE JOB_ID EXISTANT SI DISPONIBLE
        if not selected_job and existing.get("job_id"):
            job_id = existing.get("job_id")
            job = get_job_by_id(int(job_id))
            if job:
                selected_job = {
                    "id": job["id"],
                    "title": job["title"],
                    "description": job["description"]
                }
                # METTRE À JOUR LA SESSION
                session['selected_job_id'] = job_id
                session['selected_job_title'] = job["title"]

    pending_covers = session.get("pending_cover_letters", [])
    cover_letters = cover_letters + pending_covers
    # Dans upload_cv(), après extraction
    collection_cv.update_one(
        {"email": email, "type": "cv"},
        {"$set": {
            "name": fullname,
            "email": email,
            "skills": extracted["skills"],
            "job_id": job_id,  # int ou str
            "job_title": job_title,
            "updated_at": datetime.now()
        }},
        upsert=True
    )
    return render_template(
        "cv_form.html",
        name=fullname,
        email=email,
        skills=extracted["skills"],
        cover_letters=cover_letters,
        selected_job=selected_job,
        message=message
    )
@app.route("/upload_cover_letter", methods=["POST"])
def upload_cover_letter():
    file = request.files.get("cover_file")
    if not file or file.filename == '':
        return jsonify({"success": False, "message": "Fichier manquant"})

    email = session.get("user_email")
    if not email:
        return jsonify({"success": False, "message": "Connectez-vous"})

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    cover_data = {
        "type": "uploaded",
        "uploaded_filename": filename,
        "uploaded_path": file_path,
        "uploaded_at": datetime.now().isoformat()
    }

    # Stocker en session
    if "pending_cover_letters" not in session:
        session["pending_cover_letters"] = []
    session["pending_cover_letters"].append(cover_data)
    session.modified = True

    return jsonify({
        "success": True,
        "message": "Cover letter uploadée !",
        "cover": cover_data
    })
# @app.route("/save_all_data", methods=["POST"])
# def save_all_data():
#     email = session.get("user_email")
#     if not email:
#         flash("Vous devez être connecté.", "error")
#         return redirect(url_for("index"))

#     name = request.form.get("name", session.get("user_fullname"))
#     skills_raw = request.form.get("skills", "")
#     skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

#     pending = session.get("pending_cover_letters", [])
#     existing = collection_cv.find_one({"email": email, "type": "cv"})
#     old_covers = existing.get("cover_letters", []) if existing else []
#     all_covers = old_covers + pending

#     collection_cv.update_one(
#         {"email": email, "type": "cv"},
#         {"$set": {
#             "name": name,
#             "email": email,
#             "skills": skills,
#             "cover_letters": all_covers,
#             "updated_at": datetime.now()
#         }},
#         upsert=True
#     )

#     session.pop("pending_cover_letters", None)

#     # MESSAGE DE SUCCÈS
#     flash(f"Vos informations ont été sauvegardées avec succès ! ({len(all_covers)} cover{'s' if len(all_covers) > 1 else ''})", "success")
#     return redirect(url_for("index"))

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

    candidats = list(collection_cv.find({"type": "cv"}))
    return render_template("rh_dashboard.html", candidats=candidats)

# --------------------------------------
# ✅ LOGOUT
# --------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/api/run_matching/<candidate_id>')
def api_run_matching(candidate_id):
    job_id = request.args.get('job_id')
    if not job_id:
        return jsonify({"error": "job_id requis"}), 400

    result = run_matching(candidate_id, job_id, app.db)  # ← db = app.db
    return jsonify(result), (400 if "error" in result else 200)

from bson import ObjectId

@app.route('/api/candidate_jobs/<candidate_id>')
def get_candidate_jobs(candidate_id):
    try:
        candidate = None
        try:
            candidate = app.db.candidates.find_one({"_id": ObjectId(candidate_id), "type": "cv"})
        except:
            candidate = app.db.candidates.find_one({"email": candidate_id, "type": "cv"})
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        jobs = []
        if candidate.get('job_id'):
            jobs.append({
                "id": str(candidate['job_id']),
                "title": candidate.get('job_title', 'Unknown')
            })

        for cover in candidate.get('cover_letters', []):
            if cover.get('job_id'):
                jid = str(cover['job_id'])
                if not any(j['id'] == jid for j in jobs):
                    jobs.append({"id": jid, "title": cover.get('job_title', 'Unknown')})

        return jsonify({
            "candidate_id": candidate_id,
            "jobs": jobs,
            "total_jobs": len(jobs)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# --------------------------------------
# ✅ RUN
# --------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
