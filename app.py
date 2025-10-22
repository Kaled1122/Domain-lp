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
# NOTE: Using environment variable for security in real deployment
CORS(app, origins=["https://domain-lp-five.vercel.app"]) 
logging.basicConfig(level=logging.INFO)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DB_URL = os.getenv("DATABASE_URL")
if not OPENAI_KEY:
    # Use logging instead of raising Value Error to allow local testing setup
    logging.warning("Missing OPENAI_API_KEY. AI generation will fail.")
if not DB_URL:
    logging.warning("Missing DATABASE_URL. Database functions will fail.")

# Initialize components only if keys are present (for robustness)
client = OpenAI(api_key=OPENAI_KEY or "dummy_key") 
pool = SimpleConnectionPool(1, 10, dsn=DB_URL) if DB_URL else None

def get_conn(): 
    if not pool: raise Exception("Database not configured.")
    return pool.getconn()
def put_conn(c): 
    if pool: pool.putconn(c)

def safe_float(v):
    """Safely converts input to float, defaults to 0.0 on failure."""
    try: return float(v)
    except: return 0.0

def compute_total(u,a,c,b):
    """Computes the total score from four domain scores."""
    return round(safe_float(u)+safe_float(a)+safe_float(c)+safe_float(b),2)

def extract_text_from_pdf(file):
    """Extracts text from a PDF file, truncating to 5000 characters."""
    try:
        reader = PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])[:5000]
    except Exception as e:
        logging.error(f"PDF extraction failed: {e}")
        return "PDF uploaded (text extraction failed)."

# ------------------------------------------------------------
# GENERATE LESSON PLAN (GPT-4o-mini, Structured HTML)
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

        # --- Enhanced Prompt: Strict Structure and Time Allocation ---
        prompt = f"""
You are a senior English Language Teaching (ELT) instructional designer for BAE Systems.
Generate a professional, fully structured HTML lesson plan for classroom delivery, using a formal and technical tone.

REQUIREMENTS:
- Output valid HTML only (no markdown, ###, or **).
- Ensure all sections are present.
- Lesson Plan Structure stages MUST be allocated between 5 and 10 minutes each, totaling the main lesson time (e.g., if duration is 60 min, stages must sum close to 60).
- Each checklist domain must have EXACTLY 5 measurable indicators scored 5–1 (Excellent–Poor).

------------------------------------------------------------
<h2>Lesson Plan</h2>
<b>Title:</b> {a}<br>
<b>Teacher:</b> {t}<br>
<b>Duration:</b> {d}<br>
<b>CEFR Level:</b> {c}<br>
<b>Learner Profile:</b> {p}<br>

------------------------------------------------------------
<div class="objective-box">
<h3>1. Lesson Objectives</h3>
<ul>
<li>Provide AT LEAST 3 measurable, CEFR-aligned learning objectives.</li>
<li>Objective 2.</li>
<li>Objective 3.</li>
</ul>
</div>

------------------------------------------------------------
<h3>2. Lesson Plan Structure (Stages must be 5–10 minutes)</h3>
<table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#e0e7ff;font-weight:bold;text-align:left">
<th>Stage</th><th>Duration (5–10 min)</th><th>Objective/Skill</th><th>Activities</th><th>Teacher Role</th><th>Learner Role</th><th>Materials</th></tr>
<tr><td>Warm-Up</td><td>8 min</td>
<td>Activate prior knowledge related to the topic.</td>
<td>Quick group quiz or flashcard review.</td>
<td>Facilitate activity, manage timing.</td>
<td>Collaborate and recall concepts.</td>
<td>Projector, flashcards.</td></tr>
<tr><td>Presentation</td><td>10 min</td>
<td>Introduce target vocabulary and grammar structures.</td>
<td>Short lecture, explicit modeling, and checking for understanding.</td>
<td>Deliver content clearly, ask concept-checking questions.</td>
<td>Take notes, participate in checks.</td>
<td>Whiteboard, digital materials.</td></tr>
<tr><td>Practice (Controlled)</td><td>10 min</td>
<td>Reinforce new language in a controlled, guided environment.</td>
<td>Sentence completion or structured pair work exercises.</td>
<td>Monitor closely, provide error correction and scaffolding.</td>
<td>Complete structured tasks accurately.</td>
<td>Worksheets, controlled prompts.</td></tr>
<tr><td>Production (Freer)</td><td>10 min</td>
<td>Apply new language creatively in a task-based setting.</td>
<td>Role-play, group discussion, or short presentation development.</td>
<td>Support fluency, observe application, manage group dynamics.</td>
<td>Negotiate meaning, apply skills independently.</td>
<td>Markers, chart paper, case study brief.</td></tr>
<tr><td>Review & Wrap-Up</td><td>7 min</td>
<td>Consolidate learning and assign follow-up tasks.</td>
<td>Plenary feedback session and homework assignment.</td>
<td>Summarize key takeaways.</td>
<td>Reflect on learning, record homework.</td>
<td>Whiteboard, homework sheet.</td></tr>
</table>

------------------------------------------------------------
<h3>3. Supporting Details</h3>
<p><b>Purpose:</b> Promote comprehension and language accuracy through guided and creative practice relevant to technical communication.</p>
<p><b>Method:</b> Communicative and task-based approach moving from control to fluency, emphasizing professional context application.</p>
<p><b>Expected Outcome:</b> Learners will demonstrate proficiency in the objectives and can immediately apply the language skills in a simulated professional context.</p>

------------------------------------------------------------
<h3>4. Performance Domain Checklists</h3>
<p>Each area is rated 1–5 (5 = Excellent, 1 = Poor). A perfect score per domain is 25 points.</p>

<h4 style="color:#2563eb">Understanding (U) - Max 25 pts</h4>
<ul>
<li>Recognizes and accurately recalls lesson vocabulary (5–1).</li>
<li>Interprets and follows teacher instructions accurately (5–1).</li>
<li>Identifies key information and contrasts in tasks (5–1).</li>
<li>Demonstrates comprehension through correct answers (5–1).</li>
<li>Responds confidently and correctly in review questions (5–1).</li>
</ul>

<h4 style="color:#16a34a">Application (A) - Max 25 pts</h4>
<ul>
<li>Uses new grammar and vocabulary structures correctly (5–1).</li>
<li>Completes written or oral tasks independently (5–1).</li>
<li>Applies learned structures to new, unrelated contexts (5–1).</li>
<li>Transfers learning from guided activities to open production (5–1).</li>
<li>Self-corrects language errors efficiently and accurately (5–1).</li>
</ul>

<h4 style="color:#f59e0b">Communication (C) - Max 25 pts</h4>
<ul>
<li>Speaks clearly with appropriate, understandable pronunciation (5–1).</li>
<li>Interacts confidently and appropriately in pair/group tasks (5–1).</li>
<li>Produces coherent, organized, and relevant written text (5–1).</li>
<li>Uses language effectively to convey precise professional meaning (5–1).</li>
<li>Maintains fluency and clarity in extended discussion (5–1).</li>
</ul>

<h4 style="color:#dc2626">Behavior (B) - Max 25 pts</h4>
<ul>
<li>Participates actively and remains focused on tasks (5–1).</li>
<li>Shows respect, professionalism, and cooperation (5–1).</li>
<li>Follows complex, multi-step instructions promptly (5–1).</li>
<li>Supports peers effectively during collaboration (5–1).</li>
<li>Displays responsibility and consistent, high effort (5–1).</li>
</ul>

------------------------------------------------------------
<h3>5. Score Interpretation Key</h3>
<p>This section provides a guide for interpreting the total domain score (Max 100 points).</p>
<table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:50%">
<tr style="background:#059669;color:white;font-weight:bold;text-align:center"><th>Score Range</th><th>Interpretation Level</th></tr>
<tr><td style="text-align:center">90–100</td><td>Outstanding Learner</td></tr>
<tr><td style="text-align:center">75–89</td><td>Good Learner</td></tr>
<tr><td style="text-align:center">50–74</td><td>Developing Learner</td></tr>
<tr><td style="text-align:center">0–49</td><td>Needs Improvement</td></tr>
</table>

------------------------------------------------------------
<h3>6. Reflection (Instructor Review)</h3>
<ul>
<li>Which stage generated the highest learner engagement and why?</li>
<li>Were all lesson objectives achieved based on observable outcomes?</li>
<li>What improvements are needed in material adaptation or time management for future delivery?</li>
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

        html_content = resp.choices[0].message.content.strip()
        if not html_content.startswith("<html>") and not html_content.startswith("<!DOCTYPE html>"):
            # Ensure the AI's content is wrapped correctly if it didn't include the body/html tags
            html_content = f"<body>{html_content}</body>"
        
        # --- ENHANCED STYLING BLOCK ---
        styled_html = f"""
        <html>
        <head>
        <meta charset='utf-8'>
        <style>
        /* Global Resets and Typography */
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 40px;
            max-width: 900px;
            margin: 0 auto;
            line-height: 1.6;
            color: #333; /* Darker text for better contrast */
            background-color: #f7f9fc; /* Very light, subtle background */
        }}

        /* Headings and Titles */
        h2 {{
            color: #1e40af; /* Primary Navy Blue */
            border-bottom: 3px solid #60a5fa; /* Light Blue underline */
            padding-bottom: 5px;
            margin-top: 30px;
            font-size: 1.8em;
        }}
        h3 {{
            color: #3b82f6; /* Secondary Bright Blue */
            margin-top: 25px;
            font-size: 1.4em;
        }}
        h4 {{
            font-size: 1.1em;
            padding: 5px 10px;
            border-radius: 4px;
            color: white !important; 
            display: inline-block; 
        }}

        /* Objective Box - New Requirement Styling */
        .objective-box {{
            border: 2px solid #3b82f6;
            background-color: #eff6ff; /* Lightest blue background */
            padding: 15px 20px;
            border-radius: 8px;
            margin-top: 20px;
            margin-bottom: 25px;
        }}
        .objective-box h3 {{
            color: #1e40af;
            margin-top: 0;
        }}

        /* Metadata (Title/Teacher/Duration) */
        b {{
            font-weight: 600;
            color: #1f2937;
        }}
        
        /* Lists */
        ul {{
            margin-left: 20px;
            padding-left: 0;
            list-style-type: '👉 '; 
            line-height: 1.8;
        }}
        ul li {{
            padding-left: 5px;
        }}

        /* Tables (General) */
        table {{
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.05); /* Subtle shadow */
        }}
        td, th {{
            border: 1px solid #d1d5db; /* Lighter border color */
            padding: 12px 10px;
            vertical-align: top;
            text-align: left;
        }}
        th {{
            background-color: #eff6ff; /* Very light blue header background */
            color: #1e40af;
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.9em;
        }}

        /* Interpretation Key Table Styling - Target the second table specifically */
        table:last-of-type {{
            margin-top: 15px;
            border: 1px solid #059669; /* Green border for emphasis */
            box-shadow: 0 4px 6px rgba(5, 150, 100, 0.2);
        }}
        table:last-of-type th {{
            background-color: #059669 !important;
            color: white !important;
        }}

        /* Color Coding for Checklists Backgrounds */
        h4[style*="2563eb"] {{ background-color: #2563eb; }} /* Understanding (U) */
        h4[style*="16a34a"] {{ background-color: #16a34a; }} /* Application (A) */
        h4[style*="f59e0b"] {{ background-color: #f59e0b; }} /* Communication (C) */
        h4[style*="dc2626"] {{ background-color: #dc2626; }} /* Behavior (B) */

        /* Reference Source Styling */
        p:last-child {{
            margin-top: 40px;
            font-size: 0.8em;
            color: #6b7280;
            border-top: 1px dashed #d1d5db;
            padding-top: 15px;
        }}

        </style>
        </head>
        <body>{html_content}</body>
        </html>
        """
        return styled_html, 200, {"Content-Type": "text/html"}

    except Exception as e:
        logging.exception(e)
        return f"<p style='color:red'>Error during lesson generation: {e}</p>", 500

# ------------------------------------------------------------
# PERFORMANCE RECORDING
# ------------------------------------------------------------
@app.post("/save_performance")
def save_perf():
    if not pool: return jsonify({"error": "Database not configured."}), 503
    try:
        data = request.get_json(force=True)
        conn = get_conn(); cur = conn.cursor()
        for r in data:
            # Enhanced: Basic input validation before saving
            lid = r.get("lesson_id")
            rid = r.get("learner_id")
            if not lid or not rid:
                logging.warning("Skipping record due to missing ID.")
                continue

            u,a,c,b=[safe_float(r.get(k)) for k in("understanding","application","communication","behavior")]
            total=compute_total(u,a,c,b)
            
            # Using try-finally for connection management
            try:
                cur.execute("""INSERT INTO performance_records
                    (lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (lid,rid,u,a,c,b,total,datetime.now()))
            except Exception as insert_e:
                logging.error(f"Failed to insert record for {rid}: {insert_e}")
                # Optional: Handle specific PSQL errors here (e.g., missing table)
        
        conn.commit(); cur.close(); put_conn(conn)
        return jsonify({"message":f"{len(data)} records processed (saved successfully)"})
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

# ------------------------------------------------------------
# FETCH / EXPORT / BACKUP
# ------------------------------------------------------------
@app.get("/fetch_data")
def fetch_data():
    if not pool: return jsonify({"error": "Database not configured."}), 503
    try:
        lid=request.args.get("learner_id","")
        fromd=request.args.get("from","")
        tod=request.args.get("to","")
        
        q="""
            SELECT lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp 
            FROM performance_records 
            WHERE 1=1
        """
        vals=[]
        if lid:q+=" AND learner_id ILIKE %s";vals.append(f"%{lid}%")
        if fromd:q+=" AND timestamp >= %s";vals.append(fromd)
        if tod:q+=" AND timestamp <= %s";vals.append(tod)
        
        q+=" ORDER BY timestamp DESC LIMIT 1000" # Add safe limit
        
        conn=get_conn();cur=conn.cursor();cur.execute(q,tuple(vals));rows=cur.fetchall()
        cur.close();put_conn(conn)
        
        data=[{"lesson_id":r[0],"learner_id":r[1],"understanding":r[2],"application":r[3],
               "communication":r[4],"behavior":r[5],"total":r[6],"timestamp":r[7].strftime("%Y-%m-%d %H:%M")}for r in rows]
        return jsonify(data)
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

@app.get("/export_excel")
def export_excel():
    if not pool: return jsonify({"error": "Database not configured."}), 503
    try:
        conn=get_conn();
        df=pd.read_sql("SELECT * FROM performance_records ORDER BY timestamp DESC",conn)
        put_conn(conn)
        
        # Enhanced: Use a better download name including a timestamp
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_name = f"performance_records_{timestamp_str}.xlsx"
        
        buf=io.BytesIO();df.to_excel(buf,index=False);buf.seek(0)
        return send_file(buf,as_attachment=True,download_name=download_name, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

@app.get("/export_pdf")
def export_pdf():
    if not pool: return jsonify({"error": "Database not configured."}), 503
    try:
        conn=get_conn();cur=conn.cursor();
        # Fetch more comprehensive data for a report
        cur.execute("""
            SELECT lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp 
            FROM performance_records 
            ORDER BY timestamp DESC 
            LIMIT 200
        """)
        rows=cur.fetchall();cur.close();put_conn(conn)
        
        buf=io.BytesIO();
        doc=SimpleDocTemplate(buf,pagesize=A4, title="Performance Report");
        styles=getSampleStyleSheet()
        
        # Enhanced Data Table Headers
        data=[["Lesson ID", "Learner ID", "U", "A", "C", "B", "Total", "Date/Time"]]
        data+=[[r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7].strftime("%Y-%m-%d %H:%M")] for r in rows]
        
        elements=[
            Paragraph("BAE Systems Training Performance Report", styles["Title"]),
            Spacer(1, 18),
            Paragraph(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]),
            Spacer(1, 12),
            Table(data, repeatRows=1) # Repeat header row on new pages
        ]
        doc.build(elements);
        buf.seek(0)
        
        timestamp_str = datetime.now().strftime("%Y%m%d")
        download_name = f"performance_report_{timestamp_str}.pdf"
        return send_file(buf,as_attachment=True,download_name=download_name, mimetype='application/pdf')
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

@app.get("/backup_db")
def backup_db():
    if not pool: return jsonify({"error": "Database not configured."}), 503
    try:
        conn=get_conn();df=pd.read_sql("SELECT * FROM performance_records",conn);put_conn(conn)
        
        # Enhanced: Use io.BytesIO instead of writing to /tmp/ for security/robustness
        buf=io.BytesIO()
        df.to_csv(buf,index=False)
        buf.seek(0)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_name = f"db_backup_{timestamp_str}.csv"
        return send_file(buf,as_attachment=True,download_name=download_name, mimetype='text/csv')
    except Exception as e:
        logging.exception(e);return jsonify({"error":str(e)}),500

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
