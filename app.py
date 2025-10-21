import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# --------------------- OpenAI (for lesson generator) ---------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------- Database ---------------------
DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL, sslmode="require")

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

# --------------------- Helpers ---------------------
def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def compute_total(u, a, c, b):
    return round(safe_float(u) + safe_float(a) + safe_float(c) + safe_float(b), 2)

# --------------------- Lesson Plan ---------------------
@app.route("/generate_lesson", methods=["POST"])
def generate_lesson():
    try:
        teacher   = request.form.get("teacher", "")
        title     = request.form.get("lesson_title", "")
        duration  = request.form.get("duration", "")
        cefr      = request.form.get("cefr", "")
        profile   = request.form.get("profile", "")
        upfile    = request.files.get("file")

        content = ""
        if upfile:
            content = upfile.read().decode("utf-8", errors="ignore")

        prompt = f"""
You are an instructional designer at BAE Systems KSA.
Create a professional lesson plan based on the uploaded content.

Include sections:
1) Overview (Title, Teacher, Duration, CEFR, Learner Profile)
2) Measurable Objectives (U/A/C/B)
3) Materials & Resources
4) Lesson Stages (Timing | Objective | Teacher Role | Learner Role | Interaction | Procedure)
5) Domain Checklist (Understanding, Application, Communication, Behavior — 5 criteria each)
6) Interpretation Key

Lesson Title: {title}
Teacher: {teacher} | Duration: {duration} | CEFR: {cefr}
Learner Profile: {profile}

Source content:
{content}
"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role":"system","content":"You create structured ELT lesson plans with crisp tables and measurable outcomes."},
                {"role":"user","content":prompt}
            ]
        )

        html = f"""
<html><head><meta charset="utf-8">
<style>
body{{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:40px;color:#111827;line-height:1.6}}
h1{{color:#1e3a8a;font-size:24px;margin:0 0 4px}}
h2{{color:#1e40af;margin-top:24px}}
hr{{border:none;border-top:1px solid #e5e7eb;margin:16px 0}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}
th,td{{border:1px solid #e5e7eb;padding:8px;text-align:left;font-size:14px}}
thead th{{background:#f9fafb}}
</style></head><body>
<h1>{title or "Lesson Plan"}</h1>
<div>Teacher: {teacher or "-"} &nbsp;|&nbsp; CEFR: {cefr or "-"} &nbsp;|&nbsp; Duration: {duration or "-"}</div>
<hr/>
{resp.choices[0].message.content.replace("\n","<br>")}
</body></html>
"""
        return html, 200, {"Content-Type":"text/html"}

    except Exception as e:
        return f"<p style='color:red'>Error generating lesson: {e}</p>", 500

# --------------------- Save Performance ---------------------
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json(force=True)
        if not isinstance(data, list):
            return jsonify({"error": "Expected a list of performance records"}), 400

        conn = get_db()
        cur = conn.cursor()

        for r in data:
            u = safe_float(r.get("understanding"))
            a = safe_float(r.get("application"))
            c = safe_float(r.get("communication"))
            b = safe_float(r.get("behavior"))
            total = compute_total(u, a, c, b)  # server-side truth

            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                (r.get("lesson_id") or "").strip(),
                (r.get("learner_id") or "").strip(),
                u, a, c, b, total, datetime.now()
            ))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": f"{len(data)} records saved successfully."})

    except Exception as e:
        print("❌ save_performance error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- Fetch All Data (Dashboard) ---------------------
@app.route("/fetch_data", methods=["GET"])
def fetch_data():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp
            FROM performance_records
            ORDER BY timestamp DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = [{
            "record_id": r[0],
            "lesson_id": r[1],
            "learner_id": r[2] or "",
            "understanding": r[3] or 0,
            "application": r[4] or 0,
            "communication": r[5] or 0,
            "behavior": r[6] or 0,
            "total": r[7] if r[7] is not None else compute_total(r[3], r[4], r[5], r[6]),
            "timestamp": r[8].strftime("%Y-%m-%d %H:%M")
        } for r in rows]

        return jsonify(data)
    except Exception as e:
        print("❌ fetch_data error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- Maintenance: Recalculate Totals ---------------------
@app.route("/recalculate_totals", methods=["POST"])
def recalc_totals():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        UPDATE performance_records
        SET total = COALESCE(understanding,0) + COALESCE(application,0) +
                    COALESCE(communication,0) + COALESCE(behavior,0)
        WHERE total IS NULL
           OR total <> COALESCE(understanding,0) + COALESCE(application,0)
                     + COALESCE(communication,0) + COALESCE(behavior,0);
        """)
        updated = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": f"Recalculated totals for {updated} rows."})
    except Exception as e:
        print("❌ recalc_totals error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- Run ---------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
