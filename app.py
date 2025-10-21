import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL)


# ---------------------- UTILITIES ----------------------
def extract_text(file):
    name = file.filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join([page.extract_text() or "" for page in reader.pages]).strip()
    elif name.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore").strip()
    return ""


# ---------------------- ROUTES ----------------------
@app.route("/")
def home():
    return jsonify({"status": "✅ Backend connected"})


# ---------- LESSON PLAN ----------
@app.route("/generate_lesson", methods=["POST"])
def generate_lesson():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "Please upload a PDF or TXT file"}), 400

        teacher = request.form.get("teacher", "Unknown Teacher")
        lesson_title = request.form.get("lesson_title", "Untitled Lesson")
        duration = request.form.get("duration", "45 minutes")
        cefr = request.form.get("cefr", "A1")
        profile = request.form.get("profile", "Mixed")
        problems = request.form.get("problems", "None")

        text = extract_text(file)
        if not text:
            return jsonify({"error": "File is empty"}), 400

        prompt = f"""
You are an ELT instructional designer at BAE Systems KSA.
Generate a professional HTML lesson plan layout (same structure as before) with:
1. Lesson Info (Teacher, Lesson Title, Duration, CEFR, Learner Profile)
2. Lesson Objectives (Understanding, Application, Communication, Behavior)
3. Lesson Plan table (Stage | Duration | Objective | Teacher Role | Learner Role | Interaction | Details)
4. Domain Checklist (5 measurable criteria per domain — 25 points each)
5. Interpretation Key (Outstanding, Proficient, Basic, Needs Improvement, Unsatisfactory)

Use clean white layout (as before) and readable tables.

Content to base lesson on:
{text[:7000]}
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[{"role": "system", "content": prompt}],
        )
        html = res.choices[0].message.content
        return html, 200, {"Content-Type": "text/html"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- SAVE PERFORMANCE ----------
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json()
        conn = get_db()
        cur = conn.cursor()
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
            learner_id = (r.get("learner_id") or "").strip()
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
        return jsonify({"message": "✅ Records saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- DASHBOARD ----------
@app.route("/fetch_data")
def fetch_data():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT COALESCE(NULLIF(TRIM(learner_id),''),'Unlabeled') AS learner_id,
               understanding, application, communication, behavior, total, timestamp
        FROM performance_records
        WHERE learner_id IS NOT NULL
        ORDER BY timestamp DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        data = [{
            "learner_id": r[0],
            "understanding": r[1],
            "application": r[2],
            "communication": r[3],
            "behavior": r[4],
            "total": r[5],
            "timestamp": r[6].strftime("%Y-%m-%d %H:%M:%S")
        } for r in rows]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- AVERAGES ----------
@app.route("/fetch_averages")
def fetch_averages():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT COALESCE(NULLIF(TRIM(learner_id),''),'Unlabeled') AS learner_id,
               ROUND(AVG(understanding),1),
               ROUND(AVG(application),1),
               ROUND(AVG(communication),1),
               ROUND(AVG(behavior),1),
               ROUND(AVG(total),1)
        FROM performance_records
        WHERE learner_id IS NOT NULL AND TRIM(learner_id) <> ''
        GROUP BY COALESCE(NULLIF(TRIM(learner_id),''),'Unlabeled')
        ORDER BY learner_id;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        data = [{
            "learner_id": r[0],
            "understanding": r[1],
            "application": r[2],
            "communication": r[3],
            "behavior": r[4],
            "total": r[5]
        } for r in rows]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
