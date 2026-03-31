"""
app.py — TruthScan Backend (BERT Primary)
Run:  python app.py
"""

import os, re, pickle, json
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from scipy.sparse import hstack, csr_matrix

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

BASE = os.path.dirname(os.path.abspath(__file__))

def _load(name):
    path = os.path.join(BASE, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ {name} not found in {BASE}")
    with open(path, "rb") as f:
        return pickle.load(f)

# ── Load classical models ─────────────────────────────────────
print("\n🔄 Loading classical models...")
try:
    vec_word = _load("vec_word.pkl")
    vec_char = _load("vec_char.pkl")
    scaler   = _load("scaler.pkl")
    ensemble = _load("ensemble.pkl")
    models   = _load("models.pkl")
    print("✅ Classical models loaded.")
except FileNotFoundError as e:
    print(e)
    vec_word = vec_char = scaler = ensemble = models = None

# ── Load BERT ─────────────────────────────────────────────────
print("🔄 Loading BERT...")
try:
    import torch
    from transformers import BertTokenizer, BertForSequenceClassification

    BERT_DIR = os.path.join(BASE, "bert_fakenews_model") \
               if os.path.isdir(os.path.join(BASE, "bert_fakenews_model")) \
               else BASE  # flat folder fallback

    device    = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    bert_tok  = BertTokenizer.from_pretrained(BERT_DIR)
    bert_clf  = BertForSequenceClassification.from_pretrained(
                    BERT_DIR, num_labels=2).to(device)
    bert_clf.eval()
    BERT_OK   = True
    print(f"✅ BERT loaded on {device}.")
except Exception as e:
    print(f"⚠️  BERT not loaded: {e}")
    BERT_OK = False

print()

# ── Feature helpers ───────────────────────────────────────────
CLICKBAIT = {
    "breaking","exclusive","urgent","shocking","viral","exposed",
    "truth","must","share","hidden","secret","conspiracy","hoax",
    "banned","censored","leaked","watch","omg","wow","insane",
    "unbelievable","mindblowing","alert","warning","danger"
}

def clean_text(text):
    if not isinstance(text, str): return ""
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^a-zA-Z\s#@!?]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()

def extract_meta(texts, source_types):
    feats = []
    for text, stype in zip(texts, source_types):
        if not isinstance(text, str): text = ""
        words = text.split()
        n     = max(len(words), 1)
        chars = max(len(text), 1)
        feats.append([
            sum(1 for w in words if w.isupper()) / n,
            text.count("!") / chars * 100,
            text.count("?") / chars * 100,
            np.mean([len(w) for w in words]) if words else 0,
            np.log1p(len(text)),
            len(words),
            len(re.findall(r"#\w+", text)),
            len(re.findall(r"@\w+", text)),
            text.count("!!!") + text.count("???"),
            1 if re.search(r"http\S+", text) else 0,
            1 if stype == "social" else 0,
            sum(1 for w in words if w.lower() in CLICKBAIT) / n,
        ])
    return np.array(feats, dtype=np.float32)


# ── Routes ────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status"        : "ok",
        "bert_loaded"   : BERT_OK,
        "models_loaded" : ensemble is not None
    })

@app.route("/api/predict", methods=["POST"])
def predict():
    if not BERT_OK and ensemble is None:
        return jsonify({"error": "No models loaded."}), 503

    data  = request.get_json(force=True, silent=True) or {}
    text  = (data.get("text") or "").strip()
    stype = data.get("source_type", "news")

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) < 10:
        return jsonify({"error": "Text too short (min 10 chars)"}), 400

    try:
        cleaned = clean_text(text)

        # ── PRIMARY: BERT (95% accuracy) ─────────────────────
        if BERT_OK:
            import torch
            enc = bert_tok(
                cleaned,
                max_length=96,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            )
            with torch.no_grad():
                out   = bert_clf(
                    input_ids      = enc["input_ids"].to(device),
                    attention_mask = enc["attention_mask"].to(device)
                )
                probs   = torch.softmax(out.logits, dim=1)[0].cpu().numpy()
                verdict = "REAL" if probs[1] > probs[0] else "FAKE"
                real_p  = round(float(probs[1]) * 100, 1)
                fake_p  = round(float(probs[0]) * 100, 1)
        else:
            # Fallback to ensemble if BERT fails
            w       = vec_word.transform([cleaned])
            c       = vec_char.transform([cleaned])
            m       = csr_matrix(scaler.transform(
                          extract_meta([text], [stype])))
            feats   = hstack([w, c, m])
            ens_p   = ensemble.predict_proba(feats)[0]
            verdict = "REAL" if ensemble.predict(feats)[0] == 1 else "FAKE"
            real_p  = round(float(ens_p[1]) * 100, 1)
            fake_p  = round(float(ens_p[0]) * 100, 1)

        # ── SECONDARY: per-model breakdown ───────────────────
        per_model = {}
        if ensemble is not None and vec_word is not None:
            w     = vec_word.transform([cleaned])
            c     = vec_char.transform([cleaned])
            m     = csr_matrix(scaler.transform(
                        extract_meta([text], [stype])))
            feats = hstack([w, c, m])
            for name, clf in models:
                per_model[name] = (
                    "REAL" if clf.predict(feats)[0] == 1 else "FAKE"
                )
        per_model["BERT"] = verdict  # always add BERT result

        # ── Clickbait signals ─────────────────────────────────
        signals = [w for w in text.lower().split()
                   if w in CLICKBAIT][:8]

        return jsonify({
            "verdict"    : verdict,
            "real_pct"   : real_p,
            "fake_pct"   : fake_p,
            "confidence" : round(max(real_p, fake_p), 1),
            "per_model"  : per_model,
            "signals"    : signals,
            "word_count" : len(text.split()),
            "primary"    : "BERT" if BERT_OK else "Ensemble"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 TruthScan running → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
