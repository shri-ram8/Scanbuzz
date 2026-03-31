# TruthScan — Fake News Detector

Flat project. No subfolders. Drop your `.pkl` files in, run one command.

---

## Files

```
truthscan/
├── app.py            ← Flask backend (serves HTML + /api/predict)
├── index.html        ← Frontend UI
├── style.css         ← Styles
├── main.js           ← Frontend logic
├── requirements.txt  ← Python deps
├── Dockerfile        ← For Render.com
├── render.yaml       ← Render blueprint
├── .gitignore
│
├── vec_word.pkl      ← ⬇ Download from Kaggle Output tab
├── vec_char.pkl      ← ⬇
├── scaler.pkl        ← ⬇
├── ensemble.pkl      ← ⬇
└── models.pkl        ← ⬇
```

---

## Step 1 — Get model files

Finish your Kaggle notebook → **Output tab** → download:
```
vec_word.pkl  vec_char.pkl  scaler.pkl  ensemble.pkl  models.pkl
```
Paste all 5 into this folder (same level as `app.py`).

---

## Step 2 — Run locally

```bash
pip install -r requirements.txt
python app.py
```
Open → http://localhost:5000

---

## Step 3 — Deploy to Render

### Push to GitHub

```bash
git init
git lfs install
git lfs track "*.pkl"        # track large model files
git add .gitattributes
git add .
git commit -m "TruthScan"
git remote add origin https://github.com/YOU/truthscan.git
git push -u origin main
```

> If pkl files are too large for Git LFS (> 2 GB total), skip the `git lfs` steps and use Render Disk instead — see below.

### Connect to Render

1. Go to **render.com** → New → **Web Service**
2. Connect your GitHub repo
3. Render auto-reads `render.yaml` → click **Apply**
4. Build takes ~5 min
5. Your URL: `https://truthscan.onrender.com`

Every `git push` redeploys automatically.

---

## Render Disk (if pkl files > 2 GB)

1. Deploy without pkl files first
2. Render dashboard → your service → **Disks** → attach a 5 GB disk at `/app`
3. SSH into the service and upload:
   ```bash
   scp *.pkl user@your-render-host:/app/
   ```
4. Restart → models load from disk

---

## API

```
POST /api/predict
Content-Type: application/json

{ "text": "...", "source_type": "news" }   // source_type: "news" | "social"
```

Response:
```json
{
  "verdict":    "FAKE",
  "real_pct":   14.2,
  "fake_pct":   85.8,
  "confidence": 85.8,
  "per_model":  { "Logistic Regression": "FAKE", "Random Forest": "FAKE", ... },
  "signals":    ["breaking", "exposed", "shocking"],
  "word_count": 18
}
```

```
GET /api/health   →   { "status": "ok", "models_loaded": true }
```

---

## Free Tier Tip

Render free tier sleeps after 15 min idle. Use [cron-job.org](https://cron-job.org) to ping `/api/health` every 10 min — keeps it awake for free.
