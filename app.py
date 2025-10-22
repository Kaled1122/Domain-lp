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

def compute_total(u,a,c,b):
    return round(safe_float(u)+safe_float(a)+safe_float(c)+safe_float(b),2)

def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])[:5000]
    except:
        return "PDF uploaded (text extraction failed)."

# ------------------------------------------------------------
# GENERATE LESSON PLAN (GPT-4o-mini, NO StanEval)
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

        # --- Prompt: General framework, no StanEval reference ---
        prompt = f"""
You are a senior English Language Teaching (ELT) instructional designer.
Generate a professional, fully structured HTML lesson plan for classroom delivery.

REQUIREMENTS:
- Output valid HTML only (no markdown, ###, or **).
- Include sections below using <h2>, <h3>, <ul>, <li>, <p>, and <table> tags.
- Each checklist domain must have 5 measurable indicators scored 5–1 (Excellent–Poor).

------------------------------------------------------------
<h2>Lesson Plan</h2>
<b>Title:</b> {a}<br>
<b>Teacher:</b> {t}<br>
<b>Duration:</b> {d}<br>
<b>CEFR Level:</b> {c}<br>
<b>Learner Profile:</b> {p}<br>

------------------------------------------------------------
<h3>1. Lesson Objectives</h3>
<ul>
<li>Provide 3–5 measurable CEFR-aligned learning objectives.</li>
</ul>

------------------------------------------------------------
<h3>2. Lesson Plan Structure</h3>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#e0e7ff;font-weight:bold;text-align:left">
<th>Stage</th><th>Duration</th><th>Objective</th><th>Activities</th><th>Teacher Role</th><th>Learner Role</th><th>Materials</th></tr>
<tr><td>Warm-Up</td><td>10 min</td>
<td>Activate topic-related vocabulary.</td>
<td>Pair brainstorming or short Q&A.</td>
<td>Guide discussion, elicit key words.</td>
<td>Respond and share ideas.</td>
<td>Whiteboard, visuals.</td></tr>
<tr><td>Practice</td><td>20 min</td>
<td>Reinforce vocabulary and grammar.</td>
<td>Listening and fill-in exercises.</td>
<td>Monitor, correct errors.</td>
<td>Complete sentences, compare with peers.</td>
<td>Audio, worksheets.</td></tr>
<tr><td>Production</td><td>20 min</td>
<td>Apply new language in context.</td>
<td>Group project, dialogue or poster creation.</td>
<td>Support creativity, evaluate outcomes.</td>
<td>Collaborate, present work.</td>
<td>Markers, chart paper.</td></tr>
</table>

------------------------------------------------------------
<h3>3. Supporting Details</h3>
<p><b>Purpose:</b> Promote comprehension and language accuracy through guided and creative practice.</p>
<p><b>Method:</b> Communicative and task-based approach moving from control to fluency.</p>
<p><b>Expected Outcome:</b> Learners demonstrate understanding, participation, and independent use of lesson targets.</p>

------------------------------------------------------------
<h3>4. Domain Checklists</h3>
<p>Each area is rated 1–5 (5 = Excellent, 1 = Poor).</p>

<h4 style="color:#2563eb">Understanding (U)</h4>
<ul>
<li>Recognizes and recalls lesson vocabulary (5–1).</li>
<li>Understands teacher instructions accurately (5–1).</li>
<li>Identifies examples and contrasts in tasks (5–1).</li>
<li>Demonstrates comprehension through correct answers (5–1).</li>
<li>Responds confidently in review questions (5–1).</li>
</ul>

<h4 style="color:#16a34a">Application (A)</h4>
<ul>
<li>Uses new grammar and vocabulary correctly (5–1).</li>
<li>Completes written or oral tasks independently (5–1).</li>
<li>Applies learned structures to new contexts (5–1).</li>
<li>Transfers learning from guided to open activities (5–1).</li>
<li>Self-corrects simple language errors (5–1).</li>
</ul>

<h4 style="color:#f59e0b">Communication (C)</h4>
<ul>
<li>Speaks clearly with appropriate pronunciation (5–1).</li>
<li>Interacts confidently in pair/group tasks (5–1).</li>
<li>Writes coherent, organized sentences (5–1).</li>
<li>Uses language effectively for meaning (5–1).</li>
<li>Maintains fluency and clarity in extended speech (5–1).</li>
</ul>

<h4 style="color:#dc2626">Behavior (B)</h4>
<ul>
<li>Participates actively and stays on task (5–1).</li>
<li>Shows respect and cooperation (5–1).</li>
<li>Follows instructions promptly (5–1).</li>
<li>Supports peers during collaboration (5–1).</li>
<li>Displays responsibility and consistent effort (5–1).</li>
</ul>

------------------------------------------------------------
<h3>5. Reflection (Instructor Review)</h3>
<ul>
<li>Which stage generated the highest engagement?</li>
<li>Were objectives achieved according to observation?</li>
<li>What could be improved in materials or timing?</li>
</ul>

------------------------------------------------------------
<h3>Reference Source</h3>
<p>{content}</p>
"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            timeout=60,
            messages=[
                {"role": "system", "content": "Return valid HTML only — never markdown or plain text."},
                {"role": "user", "content": prompt}
            ]
        )

        html = resp.choices[0].message.content.strip()
        if not html.startswith("<html"):
            html = f"<html><body>{html}</body></html>"

        styled_html = f"""
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
        return styled_html, 200, {"Content-Type": "text/html"}

    except Exception as e:
        logging.exception(e)
        return f"<p style='color:red'>Error: {e}</p>", 500

# ------------------------------------------------------------
# PERFORMANCE RECORDING
# ------------------------------------------------------------
@app.post("/save_performance")
def save_perf():
    try:
        data = request.get_json(force=True)
        conn = get_conn(); cur = conn.cursor()
        for r in data:
            u,a,c,b=[safe_float(r.get(k)) for k in("understanding","application","communication","behavior")]
            total=compute_total(u,a,c,b)
            cur.execute("""INSERT INTO performance_records
                (lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (r.get("lesson_id"),r.get("learner_id"),u,a,c,b,total,datetime.now()))
        conn.commit(); cur.close(); put_conn(conn)
        return jsonify({"message":f"{len(data)} records saved"})
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

# ------------------------------------------------------------
# FETCH / EXPORT / BACKUP
# ------------------------------------------------------------
@app.get("/fetch_data")
def fetch_data():
    try:
        lid=request.args.get("learner_id","");fromd=request.args.get("from","");tod=request.args.get("to","")
        q="SELECT lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp FROM performance_records WHERE 1=1"
        vals=[]
        if lid:q+=" AND learner_id ILIKE %s";vals.append(f"%{lid}%")
        if fromd:q+=" AND timestamp >= %s";vals.append(fromd)
        if tod:q+=" AND timestamp <= %s";vals.append(tod)
        q+=" ORDER BY timestamp DESC"
        conn=get_conn();cur=conn.cursor();cur.execute(q,tuple(vals));rows=cur.fetchall()
        cur.close();put_conn(conn)
        data=[{"lesson_id":r[0],"learner_id":r[1],"understanding":r[2],"application":r[3],
               "communication":r[4],"behavior":r[5],"total":r[6],"timestamp":r[7].strftime("%Y-%m-%d %H:%M")}for r in rows]
        return jsonify(data)
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

@app.get("/export_excel")
def export_excel():
    try:
        conn=get_conn();df=pd.read_sql("SELECT * FROM performance_records ORDER BY timestamp DESC",conn);put_conn(conn)
        buf=io.BytesIO();df.to_excel(buf,index=False);buf.seek(0)
        return send_file(buf,as_attachment=True,download_name="records.xlsx")
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

@app.get("/export_pdf")
def export_pdf():
    try:
        conn=get_conn();cur=conn.cursor();cur.execute("SELECT learner_id,total,timestamp FROM performance_records ORDER BY timestamp DESC LIMIT 100")
        rows=cur.fetchall();cur.close();put_conn(conn)
        buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4);styles=getSampleStyleSheet()
        data=[["Learner","Total","Date"]]+[[r[0],r[1],r[2].strftime("%Y-%m-%d")]for r in rows]
        elems=[Paragraph("Performance Report",styles["Title"]),Spacer(1,12),Table(data)]
        doc.build(elems);buf.seek(0)
        return send_file(buf,as_attachment=True,download_name="report.pdf")
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

@app.get("/backup_db")
def backup_db():
    conn=get_conn();df=pd.read_sql("SELECT * FROM performance_records",conn);put_conn(conn)
    path="/tmp/backup.csv";df.to_csv(path,index=False)
    return send_file(path,as_attachment=True)

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
