import os, io, logging
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from psycopg2.pool import SimpleConnectionPool
import pandas as pd
from PyPDF2 import PdfReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from openai import OpenAI

# --- Setup ---
app = Flask(__name__)
CORS(app, origins=["https://domain-lp-five.vercel.app"])
logging.basicConfig(level=logging.INFO)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DB_URL = os.getenv("DATABASE_URL")
if not OPENAI_KEY:
    raise ValueError("Missing OPENAI_API_KEY")
if not DB_URL:
    raise ValueError("Missing DATABASE_URL")

client = OpenAI(api_key=OPENAI_KEY)
pool = SimpleConnectionPool(1, 10, dsn=DB_URL)
def get_conn(): return pool.getconn()
def put_conn(c): pool.putconn(c)

def safe_float(v):
    try:
        return float(v)
    except:
        return 0.0

def compute_total(u, a, c, b):
    return round(safe_float(u) + safe_float(a) + safe_float(c) + safe_float(b), 2)

def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])[:5000]
    except:
        return "PDF uploaded (text extraction failed)."

# --- Generate Lesson ---
@app.post("/generate_lesson")
def generate_lesson():
    try:
        f = request.form
        t, a, d, c, p = [f.get(x, "") for x in ("teacher", "lesson_title", "duration", "cefr", "profile")]
        file = request.files.get("file")
        content = extract_text_from_pdf(file) if file and file.filename.endswith(".pdf") else (file.read().decode("utf-8", errors="ignore") if file else "")

        # --- Structured StanEval Prompt ---
        prompt = f"""
You are an instructional designer at BAE Systems KSA.
Create a formal, StanEval-aligned English lesson plan following this exact structure and layout:

====================================================================
### LESSON PLAN
**Title:** {a}  
**Teacher:** {t}  
**Duration:** {d}  
**CEFR Level:** {c}  
**Learner Profile:** {p}

====================================================================
### 1. LESSON OBJECTIVES
- Write 3–5 measurable lesson objectives, linked to CEFR performance and real training outcomes.
- Each objective must start with an action verb (identify, describe, apply, explain, produce).

====================================================================
### 2. LESSON PLAN STRUCTURE (GRID)
| Stage | Duration | Objective | Activities | Teacher Role | Learner Role | Materials |
|--------|-----------|------------|-------------|---------------|---------------|------------|
| Warm-Up |  |  |  |  |  |  |
| Practice |  |  |  |  |  |  |
| Production |  |  |  |  |  |  |

====================================================================
### 3. SUPPORTING DETAILS
For each stage, include:
- **Purpose:** Why this stage exists in this lesson.
- **Method:** How this stage supports language or skill acquisition.
- **Expected Outcome:** What the learner will demonstrate by the end of the stage.

====================================================================
### 4. DOMAIN CHECKLIST (StanEval)
Provide a concise checklist under each domain with measurable indicators:

**Understanding (U)**  
-  

**Application (A)**  
-  

**Communication (C)**  
-  

**Behavior (B)**  
-  

Each indicator must correspond to lesson tasks.

====================================================================
### 5. REFLECTION (for Instructor)
- Provide 3 self-evaluation questions for the instructor about lesson delivery effectiveness.

====================================================================
**Reference Input / Source Content:**  
{content}
====================================================================

Keep the structure consistent and professional. No additional commentary or narrative.
Ensure military training context relevance and measurable performance focus.
"""

        # --- OpenAI Call ---
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            timeout=45,
            messages=[
                {"role": "system", "content": "You create professional, grid-structured lesson plans aligned with BAE StanEval domains."},
                {"role": "user", "content": prompt}
            ]
        )

        text = resp.choices[0].message.content
        html_output = f"<html><body style='font-family:Arial;padding:20px'>{text.replace(chr(10),'<br>')}</body></html>"
        return html_output, 200, {"Content-Type": "text/html"}

    except Exception as e:
        logging.exception(e)
        return f"<p style='color:red'>Error: {e}</p>", 500

# --- Save Performance ---
@app.post("/save_performance")
def save_perf():
    try:
        data = request.get_json(force=True)
        conn = get_conn()
        cur = conn.cursor()
        for r in data:
            u, a, c, b = [safe_float(r.get(k)) for k in ("understanding", "application", "communication", "behavior")]
            total = compute_total(u, a, c, b)
            cur.execute("""INSERT INTO performance_records
            (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (r.get("lesson_id"), r.get("learner_id"), u, a, c, b, total, datetime.now()))
        conn.commit()
        cur.close()
        put_conn(conn)
        return jsonify({"message": f"{len(data)} records saved"})
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Fetch Data ---
@app.get("/fetch_data")
def fetch_data():
    try:
        lid = request.args.get("learner_id", "")
        fromd = request.args.get("from", "")
        tod = request.args.get("to", "")
        q = "SELECT lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp FROM performance_records WHERE 1=1"
        vals = []
        if lid:
            q += " AND learner_id ILIKE %s"
            vals.append(f"%{lid}%")
        if fromd:
            q += " AND timestamp >= %s"
            vals.append(fromd)
        if tod:
            q += " AND timestamp <= %s"
            vals.append(tod)
        q += " ORDER BY timestamp DESC"
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(q, tuple(vals))
        rows = cur.fetchall()
        cur.close()
        put_conn(conn)
        data = [{"lesson_id": r[0], "learner_id": r[1], "understanding": r[2], "application": r[3],
                 "communication": r[4], "behavior": r[5], "total": r[6], "timestamp": r[7].strftime("%Y-%m-%d %H:%M")}
                for r in rows]
        return jsonify(data)
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Export Excel ---
@app.get("/export_excel")
def export_excel():
    try:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM performance_records ORDER BY timestamp DESC", conn)
        put_conn(conn)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="records.xlsx")
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Export PDF ---
@app.get("/export_pdf")
def export_pdf():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT learner_id, total, timestamp FROM performance_records ORDER BY timestamp DESC LIMIT 100")
        rows = cur.fetchall()
        cur.close()
        put_conn(conn)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        data = [["Learner", "Total", "Date"]] + [[r[0], r[1], r[2].strftime("%Y-%m-%d")] for r in rows]
        elems = [Paragraph("Performance Report", styles["Title"]), Spacer(1, 12), Table(data)]
        doc.build(elems)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="report.pdf")
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Backup CSV ---
@app.get("/backup_db")
def backup_db():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM performance_records", conn)
    put_conn(conn)
    path = "/tmp/backup.csv"
    df.to_csv(path, index=False)
    return send_file(path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
