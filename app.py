import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from datetime import datetime

# ------------------------------------------------------------
# ✅ SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL)

# ------------------------------------------------------------
# ✅ TEXT EXTRACTOR
# ------------------------------------------------------------
def extract_text(file):
    name = file.filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        return text.strip()
    elif name.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore").strip()
    else:
        return ""

# ------------------------------------------------------------
# ✅ ROUTES
# ------------------------------------------------------------
@app.route("/")
def home():
    return jsonify({"status": "✅ BAE Training Suite Backend Running"})

# ---------- AI LESSON PLAN GENERATOR ----------
@app.route("/generate_lesson", methods=["POST"])
def generate_lesson():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "❌ Please upload a .pdf or .txt lesson file"}), 400

        teacher = request.form.get("teacher", "Unknown Teacher")
        lesson_title = request.form.get("lesson_title", "Untitled Lesson")
        duration = request.form.get("duration", "45 minutes")
        cefr = request.form.get("cefr", "A1")
        profile = request.form.get("profile", "Mixed learners")
        problems = request.form.get("problems", "None")

        text = extract_text(file)
        if not text:
            return jsonify({"error": "❌ Could not extract text from file"}), 400

        prompt = f"""
You are an expert instructional designer at BAE Systems KSA Training Standards (StanEval).

Analyze the uploaded lesson below and generate a complete, structured HTML lesson plan.

-------------------------
Lesson Content:
{text[:6000]}
-------------------------

Use this structure:
1️⃣ Lesson Information (Teacher: {teacher}, Lesson: {lesson_title}, Duration: {duration}, CEFR: {cefr})
2️⃣ Lesson Objectives — grouped under Understanding, Application, Communication, and Behavior.
3️⃣ Lesson Plan Table — Stage | Duration | Objective | Teacher Role | Learner Role | Interaction | Supporting Details.
4️⃣ Domain Checklists — each of the 4 domains must have 5 measurable criteria (25 pts each).
5️⃣ Interpretation Key — describe what each level of domain performance means.

💡 Design Requirements:
- Clean white background, professional black text.
- Boxed layout with section headers.
- Sans-serif font, readable spacing.
- Include the teacher name and lesson title at the top.
- Make sure objectives and checklists reflect the uploaded lesson content.

Return HTML only, no Markdown fences.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[{"role": "system", "content": prompt}]
        )

        html = response.choices[0].message.content
        return html, 200, {"Content-Type": "text/html"}

    except Exception as e:
        print("❌ Generate Error:", e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# ✅ SAVE / FETCH PERFORMANCE DATA (previous features)
# ------------------------------------------------------------
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json()
        conn = get_db(); cur = conn.cursor()
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
            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application, communication, behavior, total)
                VALUES (%s,%s,%s,%s,%s,%s,%s);
            """, (
                r.get("lesson_id"),
                r.get("learner_id"),
                r.get("understanding", 0),
                r.get("application", 0),
                r.get("communication", 0),
                r.get("behavior", 0),
                r.get("total", 0)
            ))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"message": f"✅ Saved {len(data)} records successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/fetch_data")
def fetch_data():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM performance_records ORDER BY timestamp DESC;")
        rows = cur.fetchall(); cur.close(); conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# ✅ RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
