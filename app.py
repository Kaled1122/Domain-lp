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
    try: return float(v)
    except: return 0.0

def compute_total(u,a,c,b): return round(safe_float(u)+safe_float(a)+safe_float(c)+safe_float(b),2)

def extract_text_from_pdf(file):
    try:
        reader=PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])[:5000]
    except: return "PDF uploaded (text extraction failed)."

# --- Generate Lesson (Enhanced HTML + Checklists) ---
@app.post("/generate_lesson")
def generate_lesson():
    try:
        f=request.form
        t,a,d,c,p=[f.get(x,"") for x in("teacher","lesson_title","duration","cefr","profile")]
        file=request.files.get("file")
        content=extract_text_from_pdf(file) if file and file.filename.endswith(".pdf") else (
            file.read().decode("utf-8",errors="ignore") if file else ""
        )

        prompt=f"""
You are a senior instructional designer at BAE Systems KSA.
Generate a fully formatted HTML lesson plan aligned with StanEval 0098 domains.
The output must be in valid <html> format with clear headings, tables, and bullet lists.

====================================================================
<h2>LESSON PLAN</h2>
<b>Title:</b> {a}<br>
<b>Teacher:</b> {t}<br>
<b>Duration:</b> {d}<br>
<b>CEFR Level:</b> {c}<br>
<b>Learner Profile:</b> {p}<br>

====================================================================
<h3>1. LESSON OBJECTIVES</h3>
<ul>
<li>List 3–5 measurable objectives aligned with CEFR levels.</li>
<li>Use action verbs such as identify, describe, apply, explain, or produce.</li>
<li>Ensure objectives relate to operational, technical, or communicative outcomes for cadets.</li>
</ul>

====================================================================
<h3>2. LESSON PLAN STRUCTURE</h3>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#e0e7ff;font-weight:bold;text-align:left">
<td>Stage</td><td>Duration</td><td>Objective</td><td>Activities</td>
<td>Teacher Role</td><td>Learner Role</td><td>Materials</td></tr>
<tr><td>Warm-Up</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>Practice</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>Production</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</table>

====================================================================
<h3>3. SUPPORTING DETAILS</h3>
<p><b>Purpose:</b> Describe why each stage exists and how it develops skills.</p>
<p><b>Method:</b> State whether it's communicative, task-based, or accuracy-focused.</p>
<p><b>Expected Outcome:</b> Describe measurable learner performance at each stage.</p>

====================================================================
<h3>4. DOMAIN CHECKLIST (StanEval)</h3>
<p>Each domain must contain exactly five measurable performance indicators.</p>

<h4 style="color:#2563eb">Understanding (U)</h4>
<ul>
<li>Recognizes and recalls key lesson vocabulary accurately.</li>
<li>Understands instructions without repetition.</li>
<li>Demonstrates comprehension through responses or matching tasks.</li>
<li>Identifies examples and contrasts between new and known concepts.</li>
<li>Shows consistent understanding during feedback sessions.</li>
</ul>

<h4 style="color:#16a34a">Application (A)</h4>
<ul>
<li>Applies learned vocabulary or grammar in structured exercises.</li>
<li>Completes tasks independently with minimal teacher assistance.</li>
<li>Transfers knowledge from guided to open tasks accurately.</li>
<li>Uses lesson content correctly in short written or spoken form.</li>
<li>Demonstrates ability to self-correct basic mistakes.</li>
</ul>

<h4 style="color:#f59e0b">Communication (C)</h4>
<ul>
<li>Uses language to express complete ideas clearly and logically.</li>
<li>Engages in dialogues or pair work using lesson structures.</li>
<li>Responds spontaneously and meaningfully to peer questions.</li>
<li>Maintains clarity and accuracy in pronunciation or form.</li>
<li>Shows confidence in delivering extended utterances.</li>
</ul>

<h4 style="color:#dc2626">Behavior (B)</h4>
<ul>
<li>Shows punctuality and attentiveness during all activities.</li>
<li>Follows instructions promptly and cooperatively.</li>
<li>Participates actively without distraction.</li>
<li>Displays respect toward peers and instructor feedback.</li>
<li>Demonstrates teamwork and reliability during pair or group work.</li>
</ul>

====================================================================
<h3>5. REFLECTION (Instructor Review)</h3>
<ul>
<li>Which activity most effectively achieved its domain objectives?</li>
<li>What observable improvements or challenges were noted?</li>
<li>How can the materials or timing be refined for future delivery?</li>
</ul>

====================================================================
<h4>REFERENCE SOURCE</h4>
<p>{content}</p>

Return only structured HTML output—no markdown symbols or explanations.
"""

        # --- Generate lesson using GPT-4o ---
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.4,
            timeout=60,
            messages=[
                {"role": "system", "content": "You generate structured HTML lesson plans aligned with BAE StanEval domains."},
                {"role": "user", "content": prompt}
            ]
        )

        html = resp.choices[0].message.content
        if not html.strip().startswith("<"):
            html = f"<html><body><pre>{html}</pre></body></html>"

        # --- Style wrapper for iframe display ---
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

# --- Save Performance ---
@app.post("/save_performance")
def save_perf():
    try:
        data=request.get_json(force=True)
        conn=get_conn();cur=conn.cursor()
        for r in data:
            u,a,c,b=[safe_float(r.get(k)) for k in("understanding","application","communication","behavior")]
            total=compute_total(u,a,c,b)
            cur.execute("""INSERT INTO performance_records
            (lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (r.get("lesson_id"),r.get("learner_id"),u,a,c,b,total,datetime.now()))
        conn.commit();cur.close();put_conn(conn)
        return jsonify({"message":f"{len(data)} records saved"})
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

# --- Fetch Data ---
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

# --- Export Excel ---
@app.get("/export_excel")
def export_excel():
    try:
        conn=get_conn();df=pd.read_sql("SELECT * FROM performance_records ORDER BY timestamp DESC",conn);put_conn(conn)
        buf=io.BytesIO();df.to_excel(buf,index=False);buf.seek(0)
        return send_file(buf,as_attachment=True,download_name="records.xlsx")
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

# --- Export PDF ---
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

# --- Backup CSV ---
@app.get("/backup_db")
def backup_db():
    conn=get_conn();df=pd.read_sql("SELECT * FROM performance_records",conn);put_conn(conn)
    path="/tmp/backup.csv";df.to_csv(path,index=False)
    return send_file(path,as_attachment=True)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",8080)))
