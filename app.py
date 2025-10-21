import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from datetime import datetime

# ------------------------------------------------------------
# ✅ APP + DATABASE CONFIG
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL)

# ------------------------------------------------------------
# ✅ ROUTES
# ------------------------------------------------------------
@app.route("/")
def home():
    return jsonify({"status": "✅ BAE Training Suite Backend Running"})

# --- AI Lesson Plan Generator ---
@app.route("/generate_lesson", methods=["POST"])
def generate_lesson():
    try:
        data = request.get_json()
        topic = data.get("topic", "General Lesson")
        duration = data.get("duration", "45 minutes")
        cefr = data.get("cefr", "A1")

        prompt = f"""
Generate a professional lesson plan on '{topic}' (CEFR {cefr}, {duration}).
Include:
1. Lesson Objectives (Understanding, Application, Communication, Behavior)
2. Detailed Stages (Warm-up, Practice, Production, etc.)
3. Domain Checklist (5 items per domain, 25 pts each)
Return clean HTML (white background, boxed sections).
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[{"role": "system", "content": prompt}]
        )
        html = res.choices[0].message.content
        return html, 200, {"Content-Type": "text/html"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Save learner performance ---
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"error": "Invalid JSON"}), 400

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
            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application,
                 communication, behavior, total)
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
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"message": f"✅ Saved {len(data)} records successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Fetch all records ---
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
