import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from datetime import datetime

# ------------------------------------------------------------
# ✅ APP SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Railway PostgreSQL connection
DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL)

# ------------------------------------------------------------
# ✅ UTILITIES
# ------------------------------------------------------------
def extract_text(file):
    """Extract text from PDF or TXT files."""
    name = file.filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join([page.extract_text() or "" for page in reader.pages]).strip()
    elif name.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore").strip()
    return ""

# ------------------------------------------------------------
# ✅ ROUTES
# ------------------------------------------------------------
@app.route("/")
def home():
    return jsonify({"status": "✅ BAE Training Suite Backend Running"})

# ---------- LESSON PLAN GENERATOR ----------
@app.route("/generate_lesson", methods=["POST"])
def generate_lesson():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "Please upload a .pdf or .txt lesson file"}), 400

        teacher = request.form.get("teacher", "Unknown Teacher")
        lesson_title = request.form.get("lesson_title", "Untitled Lesson")
        duration = request.form.get("duration", "45 minutes")
        cefr = request.form.get("cefr", "A1")
        profile = request.form.get("profile", "Mixed learners")
        problems = request.form.get("problems", "None")

        text = extract_text(file)
        if not text:
            return jsonify({"error": "No readable text found in file"}), 400

        prompt = f"""
You are an expert instructional designer working under BAE Systems KSA Training Standards (StanEval Form 0098).

Analyze the uploaded lesson and generate a professional lesson plan in HTML.

Include:
1️⃣ Lesson Info (Teacher: {teacher}, Title: {lesson_title}, Duration: {duration}, CEFR: {cefr})
2️⃣ Lesson Objectives (Understanding, Application, Communication, Behavior)
3️⃣ Lesson Plan Table (Stage | Duration | Objective | Teacher Role | Learner Role | Interaction | Supporting Details)
4️⃣ Domain Checklists — 5 measurable items per domain (25 points each)
5️⃣ Interpretation Key — explain performance levels.

Lesson content:
{text[:6000]}

Return pure HTML styled with clean white layout, headings, and spacing.
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[{"role": "system", "content": prompt}],
        )
        html = res.choices[0].message.content
        return html, 200, {"Content-Type": "text/html"}

    except Exception as e:
        print("❌ Generate Error:", e)
        return jsonify({"error": str(e)}), 500

# ---------- PERFORMANCE REGISTER ----------
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        conn = get_db()
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
        CREATE TABLE IF NOT EXISTS performance_records (
            id SERIAL PRIMARY KEY,
            lesson_id TEXT,
            learner_id TEXT,
            understanding FLOAT,
            application FLOAT,
            communication FLOAT,
            behavior FLOAT,
            total FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        for r in data:
            learner_id = (r.get("learner_id") or "").strip()  # keep exactly as typed

            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application,
                 communication, behavior, total)
                VALUES (%s,%s,%s,%s,%s,%s,%s);
            """, (
                r.get("lesson_id"),
                learner_id,
                float(r.get("understanding", 0)),
                float(r.get("application", 0)),
                float(r.get("communication", 0)),
                float(r.get("behavior", 0)),
                float(r.get("total", 0)),
            ))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": f"✅ Saved {len(data)} records successfully"})

    except Exception as e:
        print("❌ Save Error:", e)
        return jsonify({"error": str(e)}), 500

# ---------- PERFORMANCE DASHBOARD ----------
@app.route("/fetch_data")
def fetch_data():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT COALESCE(NULLIF(TRIM(learner_id), ''), 'Unlabeled') AS learner_id,
               understanding, application, communication, behavior, total, timestamp
        FROM performance_records
        WHERE learner_id IS NOT NULL AND TRIM(learner_id) <> ''
        ORDER BY timestamp DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = [
            {
                "learner_id": r[0],
                "understanding": r[1],
                "application": r[2],
                "communication": r[3],
                "behavior": r[4],
                "total": r[5],
                "timestamp": r[6].strftime("%Y-%m-%d %H:%M:%S")
            }
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        print("❌ Fetch Error:", e)
        return jsonify({"error": str(e)}), 500

# ---------- PERFORMANCE AVERAGES (NEW TAB) ----------
@app.route("/fetch_averages")
def fetch_averages():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT COALESCE(NULLIF(TRIM(learner_id), ''), 'Unlabeled') AS learner_id,
               AVG(understanding) AS understanding,
               AVG(application) AS application,
               AVG(communication) AS communication,
               AVG(behavior) AS behavior,
               AVG(total) AS total
        FROM performance_records
        WHERE learner_id IS NOT NULL AND TRIM(learner_id) <> ''
        GROUP BY COALESCE(NULLIF(TRIM(learner_id), ''), 'Unlabeled')
        ORDER BY learner_id;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = [
            {
                "learner_id": r[0],
                "understanding": round(r[1] or 0, 1),
                "application": round(r[2] or 0, 1),
                "communication": round(r[3] or 0, 1),
                "behavior": round(r[4] or 0, 1),
                "total": round(r[5] or 0, 1)
            }
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        print("❌ Fetch Error:", e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# ✅ RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
