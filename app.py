import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from datetime import datetime

# ------------------------------------------------------------
# ✅ APP SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------
# ✅ DATABASE CONNECTION
# ------------------------------------------------------------
DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL, sslmode="require")

# ------------------------------------------------------------
# ✅ DATABASE INIT
# ------------------------------------------------------------
def init_db():
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
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ------------------------------------------------------------
# ✅ LESSON PLAN GENERATOR
# ------------------------------------------------------------
@app.route("/generate_lesson", methods=["POST"])
def generate_lesson():
    try:
        teacher = request.form.get("teacher", "")
        title = request.form.get("lesson_title", "")
        duration = request.form.get("duration", "")
        cefr = request.form.get("cefr", "")
        profile = request.form.get("profile", "")
        file = request.files.get("file")

        content = ""
        if file:
            content = file.read().decode("utf-8", errors="ignore")

        prompt = f"""
        You are an expert instructional designer working under BAE Systems KSA.
        Create a structured lesson plan with clear objectives and domain checklists.

        Lesson Title: {title}
        Teacher: {teacher}
        Duration: {duration}
        CEFR Level: {cefr}
        Learner Profile: {profile}

        Lesson content:
        {content}

        Output format:
        1. Lesson Overview
        2. Objectives (clear and measurable)
        3. Materials
        4. Procedures (stages with timing)
        5. Domain Checklist (Understanding / Application / Communication / Behavior)
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a lesson planner."},
                      {"role": "user", "content": prompt}],
            temperature=0.4,
        )

        html = f"""
        <html><head>
        <style>
        body{{font-family:Inter,sans-serif;margin:40px;color:#111827;line-height:1.6;}}
        h1{{color:#1e3a8a;font-size:24px;}}
        h2{{color:#1e40af;margin-top:24px;}}
        ul{{margin-left:20px;}}
        </style></head><body>
        <h1>{title}</h1>
        <h3>Teacher: {teacher} | CEFR: {cefr} | Duration: {duration}</h3>
        <hr/>
        {response.choices[0].message.content.replace("\n", "<br>")}
        </body></html>
        """
        return html

    except Exception as e:
        return f"<p style='color:red'>Error generating lesson: {e}</p>"

# ------------------------------------------------------------
# ✅ SAVE PERFORMANCE RECORDS
# ------------------------------------------------------------
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json(force=True)
        conn = get_db()
        cur = conn.cursor()

        for r in data:
            cur.execute("""
            INSERT INTO performance_records (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                r.get("lesson_id"),
                r.get("learner_id"),
                float(r.get("understanding") or 0),
                float(r.get("application") or 0),
                float(r.get("communication") or 0),
                float(r.get("behavior") or 0),
                float(r.get("total") or 0),
                datetime.now()
            ))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "✅ Performance data saved successfully."})
    except Exception as e:
        print("❌ Save error:", e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# ✅ FETCH ALL DATA
# ------------------------------------------------------------
@app.route("/fetch_data", methods=["GET"])
def fetch_data():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT learner_id, understanding, application, communication, behavior, total, timestamp
        FROM performance_records ORDER BY timestamp DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = []
        for r in rows:
            data.append({
                "learner_id": r[0],
                "understanding": r[1],
                "application": r[2],
                "communication": r[3],
                "behavior": r[4],
                "total": r[5],
                "timestamp": r[6].strftime("%Y-%m-%d %H:%M")
            })
        return jsonify(data)
    except Exception as e:
        print("❌ Fetch error:", e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# ✅ FETCH AVERAGES
# ------------------------------------------------------------
@app.route("/fetch_averages", methods=["GET"])
def fetch_averages():
    try:
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

        cur.execute("""
        SELECT 
            COALESCE(NULLIF(TRIM(learner_id), ''), 'Unlabeled') AS learner_id,
            ROUND(AVG(understanding), 2),
            ROUND(AVG(application), 2),
            ROUND(AVG(communication), 2),
            ROUND(AVG(behavior), 2),
            ROUND(AVG(total), 2)
        FROM performance_records
        WHERE learner_id IS NOT NULL AND TRIM(learner_id) <> ''
        GROUP BY COALESCE(NULLIF(TRIM(learner_id), ''), 'Unlabeled')
        ORDER BY learner_id;
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = []
        for r in rows:
            data.append({
                "learner_id": r[0],
                "understanding": r[1],
                "application": r[2],
                "communication": r[3],
                "behavior": r[4],
                "total": r[5]
            })

        return jsonify(data)

    except Exception as e:
        print("❌ Error in /fetch_averages:", e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# ✅ RUN APP
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
