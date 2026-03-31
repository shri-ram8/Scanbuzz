import os, re, pickle, warnings
import numpy as np
import joblib
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from scipy.sparse import hstack, csr_matrix
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

app = Flask(__name__)
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
HF_TOKEN   = os.environ.get("HF_TOKEN", "")   # set this in Render environment variables
HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

# ==============================
# 🔹 LOAD LOCAL MODELS
# ==============================
print("Loading local models...")

with open("vec_word.pkl", "rb") as f: vec_word = pickle.load(f)
with open("vec_char.pkl", "rb") as f: vec_char = pickle.load(f)
with open("scaler.pkl",   "rb") as f: scaler   = pickle.load(f)
with open("ensemble.pkl", "rb") as f: ensemble = pickle.load(f)
with open("models.pkl",   "rb") as f: models_list = pickle.load(f)
# models_list = [("Logistic Regression", lr), ("XGBoost", xgb), ("LightGBM", lgbm)]

print("All local models loaded ✅")

# ==============================
# 🔹 TEXT HELPERS (same as training)
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

def build_features(text, source_type="news"):
    cleaned = clean_text(text)
    w    = vec_word.transform([cleaned])
    c    = vec_char.transform([cleaned])
    meta = csr_matrix(scaler.transform(
        extract_meta_features([text], [source_type])
    ))
    return hstack([w, c, meta])

# ==============================
# 🔹 BERT PREDICTION (HuggingFace)
# ==============================
def predict_bert(text):
    try:
        response = requests.post(
            HF_API_URL,
            headers=HF_HEADERS,
            json={"inputs": text},
            timeout=15
        )
        if response.status_code != 200:
            return {"label": "error", "verdict": "UNKNOWN", "confidence": 0}

        result = response.json()

        # HF returns list of list: [[{label, score}, {label, score}]]
        # or list: [{label, score}, {label, score}]
        if isinstance(result, list) and isinstance(result[0], list):
            result = result[0]

        # Find the highest scored label
        best = max(result, key=lambda x: x["score"])
        raw_label = best["label"]   # "LABEL_0" or "LABEL_1"
        score     = best["score"]

        # LABEL_1 = Real, LABEL_0 = Fake
        verdict = "REAL" if raw_label == "LABEL_1" else "FAKE"

        return {
            "label"     : raw_label,
            "verdict"   : verdict,
            "confidence": round(score * 100, 2)
        }
    except requests.exceptions.Timeout:
        return {"label": "timeout", "verdict": "UNKNOWN", "confidence": 0, "error": "HuggingFace API timed out"}
    except Exception as e:
        return {"label": "error", "verdict": "UNKNOWN", "confidence": 0, "error": str(e)}

# ==============================
# 🔹 LOCAL MODELS PREDICTION
# ==============================
def predict_local(text, source_type="news"):
    feats = build_features(text, source_type)

    # Individual model predictions
    individual = {}
    for name, clf in models_list:
        pred  = clf.predict(feats)[0]
        proba = clf.predict_proba(feats)[0]
        individual[name] = {
            "verdict"    : "REAL" if pred == 1 else "FAKE",
            "confidence" : round(float(max(proba)) * 100, 2),
            "real_prob"  : round(float(proba[1]) * 100, 2),
            "fake_prob"  : round(float(proba[0]) * 100, 2),
        }

    # Ensemble prediction
    ens_pred  = ensemble.predict(feats)[0]
    ens_proba = ensemble.predict_proba(feats)[0]
    ensemble_result = {
        "verdict"   : "REAL" if ens_pred == 1 else "FAKE",
        "confidence": round(float(max(ens_proba)) * 100, 2),
        "real_prob" : round(float(ens_proba[1]) * 100, 2),
        "fake_prob" : round(float(ens_proba[0]) * 100, 2),
    }

    return {
        "individual": individual,
        "ensemble"  : ensemble_result
    }

# ==============================
# 🔹 MAIN PREDICT ENDPOINT
# ==============================
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text        = data.get("text", "").strip()
    source_type = data.get("source_type", "news")   # "news" or "social"

    if not text:
        return jsonify({"error": "Text cannot be empty"}), 400

    # Run BERT (primary) and local models (display only)
    bert_result  = predict_bert(text)
    local_result = predict_local(text, source_type)

    return jsonify({
        "input"      : text[:200],                    # echo back for frontend
        "source_type": source_type,
        "bert"       : bert_result,                   # PRIMARY verdict
        "local"      : local_result,                  # supporting predictions
    })

# ==============================
# 🔹 HEALTH CHECK
# ==============================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "models_loaded": True})

# ==============================
# 🔹 RUN
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
