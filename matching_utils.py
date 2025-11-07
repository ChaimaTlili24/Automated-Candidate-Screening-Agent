# matching_utils.py
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Initialisation NLTK (une seule fois)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet')

stop_words = set(stopwords.words('english'))
lemmatizer = WordNetLemmatizer()
model = SentenceTransformer('sbert_model')


def preprocess_skills(text):
    """
    Nettoie et lemmatise les compétences
    """
    if not text:
        return ""
    pattern_skills = re.compile(r'[^A-Za-z0-9+#\.\s]')
    text = pattern_skills.sub(" ", str(text)).lower()
    tokens = word_tokenize(text)
    tokens = [t for t in tokens if len(t) > 1 and t not in stop_words]
    lemmas = []
    seen = set()
    for t in tokens:
        l = lemmatizer.lemmatize(t, pos='v')
        if l == t:
            l = lemmatizer.lemmatize(t, pos='n')
        if l not in seen:
            seen.add(l)
            lemmas.append(l)
    return " ".join(lemmas)


def extract_technical_skills(skills_list):
    """
    Convertit une liste ou string de compétences en texte prétraité
    """
    if not skills_list:
        return ""
    if isinstance(skills_list, list):
        skills_text = " ".join([str(s) for s in skills_list])
    else:
        skills_text = str(skills_list)
    return preprocess_skills(skills_text)


# EN-TÊTE CONSERVÉE — FONCTIONNE AVEC app.db
def run_matching(candidate_id, job_id, db):
    """
    Exécute le matching entre un candidat et un job
    candidate_id : str(ObjectId) ou email
    job_id      : int (SQLite ID)
    db          : app.db → avec .candidates, .matching_results, .get_sqlite_db
    """
    try:
        from bson import ObjectId
        from datetime import datetime

        # === 1. RÉCUPÉRER LE CANDIDAT (MongoDB) ===
        candidate = None
        try:
            candidate = db.candidates.find_one({"_id": ObjectId(candidate_id), "type": "cv"})
        except:
            pass
        if not candidate:
            candidate = db.candidates.find_one({"email": candidate_id, "type": "cv"})
        if not candidate:
            return {"error": "Candidate not found"}

        # === 2. RÉCUPÉRER LE JOB (SQLite) ===
        sqlite_db = db.get_sqlite_db()
        cursor = sqlite_db.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        job_row = cursor.fetchone()
        if not job_row:
            return {"error": "Job not found"}
        job = dict(job_row)

        # === 3. PRÉTRAITEMENT DES COMPÉ || COMPÉTENCES ===
        cand_skills = extract_technical_skills(candidate.get('skills', []))
        job_skills = extract_technical_skills(job.get('required_skills') or job.get('description', ''))

        if not cand_skills.strip():
            return {"error": "No candidate skills"}
        if not job_skills.strip():
            return {"error": "No job skills"}

        # === 4. CALCUL DE SIMILARITÉ ===
        cand_emb = model.encode([cand_skills])
        job_emb = model.encode([job_skills])
        similarity = cosine_similarity(cand_emb, job_emb)[0][0]

        # CORRECTION CRITIQUE : np.float32 → float Python
        match_score = round(float(similarity) * 100, 2)

        # === 5. SAUVEGARDE DU RÉSULTAT ===
        result = {
            "candidate_id": str(candidate["_id"]),
            "candidate_name": str(candidate.get('name', 'Unknown')),
            "candidate_email": str(candidate.get('email', 'unknown@email.com')),
            "job_id": str(job_id),
            "job_title": str(job.get('title', 'Unknown')),
            "match_score": match_score,  # float Python natif
            "matched_at": datetime.now().isoformat()
        }

        # Sauvegarde dans matching_results
        db.matching_results.update_one(
            {"candidate_id": candidate["_id"], "job_id": str(job_id)},
            {"$set": result},
            upsert=True
        )

        # Mise à jour du score Phase 0
        db.candidates.update_one(
            {"_id": candidate["_id"]},
            {"$set": {
                "phase0_score": match_score,
                "last_matched_at": datetime.now()
            }}
        )

        return result

    except Exception as e:
        return {"error": f"Matching failed: {str(e)}"}