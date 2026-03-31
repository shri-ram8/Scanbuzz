import os, re, pickle, warnings
import numpy as np
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from scipy.sparse import hstack, csr_matrix

warnings.filterwarnings("ignore")

app = Flask(__name__, static_folder=".")
CORS(app)

# ==============================
# 🔹 CONSTANTS
# ==============================
CLICKBAIT_WORDS = {
    "breaking","exclusive","urgent","shocking","viral","exposed",
    "truth","must","share","hidden","secret","conspiracy","hoax",
    "banned","censored","leaked","watch","omg","wow","insane",
    "unbelievable","mindblowing","alert","warning","danger"
}

HF_API_URL = "https://api-inference.huggingface.co/models/ramsulochana/truthscan-bert"
HF_TOKEN   = os.environ.get("HF_TOKEN", "")
HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

# ==============================
# 🔹 LOAD LOCAL MODELS
# ==============================
print("🔄 Loading classical models...")

with open("vec_word.pkl", "rb") as f: vec_word    = pickle.load(f)
with open("vec_char.pkl", "rb") as f: vec_char    = pickle.load(f)
with open("scaler.pkl",   "rb") as f: scaler      = pickle.load(f)
with open("ensemble.pkl", "rb") as f: ensemble    = pickle.load(f)
with open("models.pkl",   "rb") as f: models_list = pickle.load(f)
# models_list = [("Logistic Regression", lr), ("XGBoost", xgb), ("LightGBM", lgbm)]

print("✅ Classical models loaded.")

# ==============================
# 🔹 TEXT HELPERS (identical to training notebook)
# ==============================
def clean_text(text):
    if not isinstance(text, str): return ""
    text = re.sub(r'http\S+|www\.\S+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^a-zA-Z\s#@!?]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()

def extract_meta_features(texts, source_types):
    feats = []
    for text, stype in zip(texts, source_types):
        if not isinstance(text, str): text = ""
        words = text.split()
        n     = max(len(words), 1)
        chars = max(len(text), 1)
        feats.append([
            sum(1 for w in words if w.isupper()) / n,
            text.count('!') / chars * 100,
            text.count('?') / chars * 100,
            np.mean([len(w) for w in words]) if words else 0,
            np.log1p(len(text)),
            len(words),
            len(re.findall(r'#\w+', text)),
            len(re.findall(r'@\w+', text)),
            text.count('!!!') + text.count('???'),
            1 if re.search(r'http\S+', text) else 0,
            1 if stype == "social" else 0,
            sum(1 for w in words if w.lower() in CLICKBAIT_WORDS) / n,
        ])
    return np.array(feats, dtype=np.float32)

def extract_signals(text):
    """Return clickbait words found in text — shown as tags in UI."""
    words = text.lower().split()
    found = []
    for w in words:
        clean = re.sub(r'[^a-z]', '', w)
        if clean in CLICKBAIT_WORDS and clean not in found:
            found.append(clean)
    return found

def build_features(text, source_type="news"):
    cleaned = clean_text(text)
    w    = vec_word.transform([cleaned])
    c    = vec_char.transform([cleaned])
    meta = csr_matrix(scaler.transform(
        extract_meta_features([text], [source_type])
    ))
    return hstack([w, c, meta])

# ==============================
# 🔹 BERT PREDICTION
# ==============================
def predict_bert(text):
    try:
        response = requests.post(
            HF_API_URL,
            headers=HF_HEADERS,
            json={"inputs": text},
            timeout=20
        )
        if response.status_code != 200:
            return None

        result = response.json()

        # HF returns [[{label,score},...]] or [{label,score},...]
        if isinstance(result, list) and isinstance(result[0], list):
            result = result[0]

        # LABEL_1 = Real, LABEL_0 = Fake
        scores    = {item["label"]: item["score"] for item in result}
        real_prob = scores.get("LABEL_1", 0.5)
        fake_prob = scores.get("LABEL_0", 0.5)

        verdict    = "REAL" if real_prob >= fake_prob else "FAKE"
        confidence = round(max(real_prob, fake_prob) * 100, 1)

        return {
            "verdict"   : verdict,
            "real_prob" : round(real_prob * 100, 1),
            "fake_prob" : round(fake_prob * 100, 1),
            "confidence": confidence
        }
    except Exception:
        return None

# ==============================
# 🔹 LOCAL MODELS PREDICTION
# ==============================
def predict_local(text, source_type="news"):
    feats     = build_features(text, source_type)
    per_model = {}

    for name, clf in models_list:
        pred           = clf.predict(feats)[0]
        per_model[name] = "REAL" if pred == 1 else "FAKE"

    # Ensemble fallback
    ens_pred  = ensemble.predict(feats)[0]
    ens_proba = ensemble.predict_proba(feats)[0]

    return {
        "verdict"  : "REAL" if ens_pred == 1 else "FAKE",
        "real_prob": round(float(ens_proba[1]) * 100, 1),
        "fake_prob": round(float(ens_proba[0]) * 100, 1),
        "per_model": per_model
    }

# ==============================
# 🔹 SERVE FRONTEND FILES
# ==============================
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    # Don't intercept API routes
    if filename.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(".", filename)

# ==============================
# 🔹 PREDICT — matches frontend fetch('/api/predict')
# ==============================
@app.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text        = data.get("text", "").strip()
    source_type = data.get("source_type", "news")

    if not text:
        return jsonify({"error": "Text cannot be empty"}), 400

    word_count = len(text.split())
    signals    = extract_signals(text)

    # 1️⃣ BERT — primary verdict
    bert = predict_bert(text)

    # 2️⃣ Local models — supporting display
    local = predict_local(text, source_type)

    # 3️⃣ Final verdict: BERT if available, else ensemble fallback
    if bert:
        verdict    = bert["verdict"]
        real_pct   = bert["real_prob"]
        fake_pct   = bert["fake_prob"]
        confidence = bert["confidence"]
        primary    = "BERT"
    else:
        verdict    = local["verdict"]
        real_pct   = local["real_prob"]
        fake_pct   = local["fake_prob"]
        confidence = round(max(local["real_prob"], local["fake_prob"]), 1)
        primary    = "Ensemble (fallback)"

    # 4️⃣ per_model for frontend model breakdown section
    # frontend does: Object.entries(d.per_model).map(([name, v]) => ...)
    per_model = {"BERT": verdict}        # BERT shown first
    per_model.update(local["per_model"]) # LR, XGBoost, LightGBM

    return jsonify({
        "verdict"   : verdict,     # "REAL" or "FAKE"
        "confidence": confidence,  # 92.3
        "real_pct"  : real_pct,    # 92.3
        "fake_pct"  : fake_pct,    # 7.7
        "word_count": word_count,  # 28
        "primary"   : primary,     # "BERT"
        "signals"   : signals,     # ["breaking","hidden",...]
        "per_model" : per_model,   # {"BERT":"REAL","Logistic Regression":"REAL",...}
    })

# ==============================
# 🔹 HEALTH CHECK
# ==============================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ==============================
# 🔹 RUN
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Running on {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
