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

# ------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------
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
    try: return float(v)
    except: return 0.0

def compute_total(u, a, c, b):
    return round(safe_float(u) + safe_float(a) + safe_float(c) + safe_float(b), 2)

def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])[:5000]
    except:
        return "PDF uploaded (text extraction failed)."

# ------------------------------------------------------------
# GENERATE LESSON PLAN — GPT-4o-mini (HTML OUTPUT)
# ------------------------------------------------------------
@app.post("/generate_lesson")
def generate_lesson():
    try:
        f = request.form
        t, a, d, c, p = [f.get(x, "") for x in ("teacher", "lesson_title", "duration", "cefr", "profile")]
        file = request.files.get("file")
        content = extract_text_from_pdf(file) if file and file.filename.endswith(".pdf") else (
            file.read().decode("utf-8", errors="ignore") if file else ""
        )

        prompt = f"""
You are a senior instructional designer at BAE Systems KSA.
You must return a **fully formatted HTML lesson plan** ONLY — no markdown, no plain text.

STRUCTURE:
1. <h2>Lesson Plan</h2> — include Title, Teacher, Duration, CEFR, Learner Profile.
2. <h3>Lesson Objectives</h3> — 3–5 measurable CEFR-aligned objectives.
3. <h3>Lesson Plan Structure</h3> — Table (Warm-Up, Practice, Production).
4. <h3>Supporting Details</h3> — Purpose, Method, Expected Outcome.
5. <h3>Domain Checklist (StanEval)</h3> — EXACTLY five measurable indicators per domain (U, A, C, B).
6. <h3>Reflection (Instructor Review)</h3> — 3 reflective questions.
7. <h3>Reference Source</h3> — summarize uploaded content.

Styling:
- Use <table>, <ul>, <li>, <p>, <b> only.
- Add subtle borders (#ccc) and soft table header background (#f3f4f6).
- Font: Arial; headings color #1e3a8a; text color #1f2937.

Lesson:
Title: {a}
Teacher: {t}
Duration: {d}
CEFR Level: {c}
Learner Profile: {p}

Reference Input:
{content}
"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            timeout=60,
            messages=[
                {"role": "system", "content": "Return only valid HTML. Never use markdown symbols like ** or ###."},
                {"role": "user", "content": prompt}
            ]
        )

        html = resp.choices[0].message.content.strip()

        if not html.startswith("<html"):
            html = f"<html><body>{html}</body></html>"

        wrapped_html = f"""
        <html>
        <head>
        <meta charset='utf-8'>
        <style>
        body{{font-family:Arial,Helvetica,sans-serif;padding:30px;line-height:1.6;color:#1f2937;}}
        h2,h3,h4{{color:#1e3a8a;margin-top:1.2em;}}
        table{{border-collapse:collapse;width:100%;margin-top:1em;}}
        td,th{{border:1px solid #ccc;padding:8px;vertical-align:top;}}
        th{{background:#f3f4f6;}}
        ul{{margin-left:20px;}}
        </style>
        </head>
        <body>{html}</body>
        </html>
        """

        return wrapped_html, 200, {"Content-Type": "text/html"}

    except Exception as e:
        logging.exception(e)
        return f"<p style='color:red'>Error: {e}</p>", 500

# ------------------------------------------------------------
# SAVE PERFORMANCE DATA
# ------------------------------------------------------------
@app.post("/save_performance")
def save_perf():
    try:
        data = request.get_json(force=True)
        conn = get_conn(); cur = conn.cursor()
        for r in data:
            u, a, c, b = [safe_float(r.get(k)) for k in ("understanding","application","communication","behavior")]
            total = compute_total(u, a, c, b)
            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (r.get("lesson_id"), r.get("learner_id"), u, a, c, b, total, datetime.now()))
        conn.commit(); cur.close(); put_conn(conn)
        return jsonify({"message": f"{len(data)} records saved"})
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# FETCH DATA (FILTERABLE)
# ------------------------------------------------------------
@app.get("/fetch_data")
def fetch_data():
    try:
        lid = request.args.get("learner_id", "")
        fromd = request.args.get("from", "")
        tod = request.args.get("to", "")
        q = """SELECT lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp 
               FROM performance_records WHERE 1=1"""
        vals = []
        if lid:
            q += " AND learner_id ILIKE %s"; vals.append(f"%{lid}%")
        if fromd:
            q += " AND timestamp >= %s"; vals.append(fromd)
        if tod:
            q += " AND timestamp <= %s"; vals.append(tod)
        q += " ORDER BY timestamp DESC"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(q, tuple(vals)); rows = cur.fetchall()
        cur.close(); put_conn(conn)
        data = [
            {
                "lesson_id": r[0], "learner_id": r[1],
                "understanding": r[2], "application": r[3],
                "communication": r[4], "behavior": r[5],
                "total": r[6], "timestamp": r[7].strftime("%Y-%m-%d %H:%M")
            }
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
# EXPORTS (EXCEL / PDF / CSV BACKUP)
# ------------------------------------------------------------
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


@app.get("/export_pdf")
def export_pdf():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT learner_id, total, timestamp FROM performance_records ORDER BY timestamp DESC LIMIT 100")
        rows = cur.fetchall(); cur.close(); put_conn(conn)
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


@app.get("/backup_db")
def backup_db():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM performance_records", conn)
    put_conn(conn)
    path = "/tmp/backup.csv"
    df.to_csv(path, index=False)
    return send_file(path, as_attachment=True)

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
