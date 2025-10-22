import os, io, re, json, logging
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
CORS(app, resources={r"/*": {"origins": "https://domain-lp-five.vercel.app"}})
logging.basicConfig(level=logging.INFO)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DB_URL = os.getenv("DATABASE_URL")

if not OPENAI_KEY:
    logging.warning("⚠️ Missing OPENAI_API_KEY — AI generation will fail.")
if not DB_URL:
    logging.warning("⚠️ Missing DATABASE_URL — Database functions will fail.")

client = OpenAI(api_key=OPENAI_KEY or "dummy_key")
pool = SimpleConnectionPool(1, 10, dsn=DB_URL) if DB_URL else None


# ------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------
def get_conn():
    if not pool:
        raise Exception("Database not configured.")
    return pool.getconn()


def put_conn(c):
    if pool:
        pool.putconn(c)


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
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        return text[:5000]
    except Exception as e:
        logging.error(f"PDF extraction failed: {e}")
        return "PDF uploaded (text extraction failed)."


# ------------------------------------------------------------
# LESSON PLAN GENERATOR
# ------------------------------------------------------------
def generate_lesson_plan_text(teacher, title, duration, cefr, profile, content):
    """Generate a full HTML-based lesson plan including structure table and domain checklists."""
    system_prompt = """
You are a senior English Language Teaching (ELT) instructional designer for BAE Systems.

Generate a professional, **fully structured HTML lesson plan** for classroom delivery using a formal instructional tone.

Requirements:
- Output valid, self-contained HTML only (no markdown, no JSON).
- Include the following structure exactly as described.

------------------------------------------------------------
<h2>Lesson Plan</h2>
<b>Title:</b> {title}<br>
<b>Teacher:</b> {teacher}<br>
<b>Duration:</b> {duration}<br>
<b>CEFR Level:</b> {cefr}<br>
<b>Learner Profile:</b> {profile}<br>

------------------------------------------------------------
<h3>1. Lesson Objectives</h3>
<ul>
<li>List at least 3 measurable, CEFR-aligned objectives using action verbs (e.g., identify, describe, produce).</li>
</ul>

------------------------------------------------------------
<h3>2. Lesson Plan Structure</h3>
<table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#e0e7ff;font-weight:bold;text-align:left">
<th>Stage</th><th>Duration</th><th>Objective/Skill</th><th>Activities</th><th>Teacher Role</th><th>Learner Role</th><th>Materials</th>
</tr>
<tr><td>Warm-Up</td><td>5–10 min</td><td>Activate prior knowledge</td><td>Brief discussion or brainstorming.</td><td>Facilitates, elicits ideas.</td><td>Responds and participates actively.</td><td>Board, visuals.</td></tr>
<tr><td>Presentation</td><td>10 min</td><td>Introduce key language points.</td><td>Model target vocabulary and grammar.</td><td>Explains, demonstrates, checks understanding.</td><td>Listens and takes notes.</td><td>Board, projector.</td></tr>
<tr><td>Practice (Controlled)</td><td>10 min</td><td>Reinforce understanding through repetition.</td><td>Sentence gap-fill, matching or drill tasks.</td><td>Monitors, provides correction.</td><td>Practices accurately in pairs.</td><td>Worksheets, flashcards.</td></tr>
<tr><td>Production (Freer)</td><td>10 min</td><td>Apply target language creatively.</td><td>Role-play or open discussion.</td><td>Facilitates and observes.</td><td>Uses new language spontaneously.</td><td>Real-life prompts.</td></tr>
<tr><td>Review & Wrap-Up</td><td>5 min</td><td>Summarize and reflect.</td><td>Recap lesson and assign homework.</td><td>Highlights key takeaways.</td><td>Reflects and asks questions.</td><td>Notebook, homework sheet.</td></tr>
</table>

------------------------------------------------------------
<h3>3. Supporting Details</h3>
<p><b>Purpose:</b> Explain how the lesson supports learners’ communicative competence.</p>
<p><b>Method:</b> Mention approach (e.g., communicative, task-based).</p>
<p><b>Expected Outcome:</b> Describe how learners will demonstrate mastery.</p>

------------------------------------------------------------
<h3>4. Performance Domain Checklists</h3>
<p>Each domain is rated 1–5 (5=Excellent, 1=Poor). Each domain totals 25 points.</p>

<h4 style="color:#2563eb">Understanding (U)</h4>
<ul>
<li>Recognizes and recalls target vocabulary accurately (5–1).</li>
<li>Interprets key instructions correctly (5–1).</li>
<li>Identifies information in listening/reading tasks (5–1).</li>
<li>Answers comprehension questions appropriately (5–1).</li>
<li>Demonstrates understanding in responses (5–1).</li>
</ul>

<h4 style="color:#16a34a">Application (A)</h4>
<ul>
<li>Uses new grammar and vocabulary in context (5–1).</li>
<li>Applies learned rules accurately in tasks (5–1).</li>
<li>Adapts examples to new sentences (5–1).</li>
<li>Connects lesson content to real-life contexts (5–1).</li>
<li>Self-corrects errors effectively (5–1).</li>
</ul>

<h4 style="color:#f59e0b">Communication (C)</h4>
<ul>
<li>Speaks clearly and understandably (5–1).</li>
<li>Maintains interaction in pairs or groups (5–1).</li>
<li>Writes coherent, organized sentences (5–1).</li>
<li>Expresses ideas fluently with few pauses (5–1).</li>
<li>Uses appropriate tone and register (5–1).</li>
</ul>

<h4 style="color:#dc2626">Behavior (B)</h4>
<ul>
<li>Participates actively throughout class (5–1).</li>
<li>Shows cooperation and teamwork (5–1).</li>
<li>Respects time and instructions (5–1).</li>
<li>Supports peers positively (5–1).</li>
<li>Demonstrates motivation and effort (5–1).</li>
</ul>

------------------------------------------------------------
<h3>5. Score Interpretation Key</h3>
<table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:50%">
<tr style="background:#059669;color:white;font-weight:bold;text-align:center"><th>Score Range</th><th>Performance Level</th></tr>
<tr><td style="text-align:center">90–100</td><td>Outstanding</td></tr>
<tr><td style="text-align:center">75–89</td><td>Good</td></tr>
<tr><td style="text-align:center">50–74</td><td>Developing</td></tr>
<tr><td style="text-align:center">0–49</td><td>Needs Improvement</td></tr>
</table>

------------------------------------------------------------
<h3>6. Reflection (Instructor Review)</h3>
<ul>
<li>What activity generated the most engagement and why?</li>
<li>Were objectives achieved? How can future lessons improve?</li>
<li>What strategies enhanced comprehension and participation?</li>
</ul>

------------------------------------------------------------
<h3>7. Reference Source</h3>
<p>{content}</p>
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role": "system", "content": system_prompt.format(
                    title=title, teacher=teacher, duration=duration, cefr=cefr, profile=profile, content=content
                )}
            ],
        )
        html = response.choices[0].message.content.strip()
        html = re.sub(r"^```(?:html)?|```$", "", html, flags=re.MULTILINE).strip()
        html = html.replace("\\n", "\n").replace('\\"', '"')
        return html
    except Exception as e:
        logging.error(f"AI generation failed: {e}")
        return f"<p style='color:red'>AI generation failed: {e}</p>"


# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK", "message": "Domain Lesson Planner Backend Active"})


@app.post("/generate_lesson")
def generate_lesson():
    try:
        f = request.form
        teacher = f.get("teacher", "")
        title = f.get("lesson_title", "")
        duration = f.get("duration", "")
        cefr = f.get("cefr", "")
        profile = f.get("profile", "")
        file = request.files.get("file")

        content = ""
        if file:
            if file.filename.endswith(".pdf"):
                content = extract_text_from_pdf(file)
            else:
                content = file.read().decode("utf-8", errors="ignore")

        html_output = generate_lesson_plan_text(teacher, title, duration, cefr, profile, content)

        # Optional DB save
        if pool:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS lessons (
                        id SERIAL PRIMARY KEY,
                        teacher TEXT,
                        title TEXT,
                        cefr TEXT,
                        profile TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        html TEXT
                    );
                """)
                cur.execute(
                    "INSERT INTO lessons (teacher, title, cefr, profile, html) VALUES (%s, %s, %s, %s, %s);",
                    (teacher, title, cefr, profile, html_output),
                )
                conn.commit()
                cur.close()
                put_conn(conn)
            except Exception as e:
                logging.warning(f"DB insert failed: {e}")

        return jsonify({"status": "success", "html": html_output})

    except Exception as e:
        logging.error(f"Error in /generate_lesson: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.post("/download_pdf")
def download_pdf():
    """Generate and return PDF of lesson HTML."""
    try:
        html_content = request.form.get("html", "")
        if not html_content:
            return jsonify({"error": "No HTML content provided"}), 400

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [Paragraph("Lesson Plan", styles["Title"]), Spacer(1, 12)]
        story.append(Paragraph(html_content.replace("\n", "<br/>"), styles["BodyText"]))
        doc.build(story)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"lesson_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        )
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------
# PERFORMANCE ROUTES
# ------------------------------------------------------------
@app.post("/save_performance")
def save_perf():
    if not pool:
        return jsonify({"error": "Database not configured."}), 503
    try:
        data = request.get_json(force=True)
        conn = get_conn()
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
                timestamp TIMESTAMP DEFAULT NOW()
            );
        """)
        for r in data:
            lid = r.get("lesson_id")
            rid = r.get("learner_id")
            if not lid or not rid:
                continue
            u,a,c,b = [safe_float(r.get(k)) for k in ("understanding","application","communication","behavior")]
            total = compute_total(u,a,c,b)
            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (lid,rid,u,a,c,b,total,datetime.now()))
        conn.commit()
        cur.close()
        put_conn(conn)
        return jsonify({"message": f"{len(data)} records saved successfully."})
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500


@app.get("/fetch_data")
def fetch_data():
    if not pool:
        return jsonify({"error": "Database not configured."}), 503
    try:
        lid=request.args.get("learner_id","")
        fromd=request.args.get("from","")
        tod=request.args.get("to","")
        q="SELECT lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp FROM performance_records WHERE 1=1"
        vals=[]
        if lid:
            q+=" AND learner_id ILIKE %s"; vals.append(f"%{lid}%")
        if fromd:
            q+=" AND timestamp >= %s"; vals.append(fromd)
        if tod:
            q+=" AND timestamp <= %s"; vals.append(tod)
        q+=" ORDER BY timestamp DESC LIMIT 1000"
        conn=get_conn(); cur=conn.cursor(); cur.execute(q,tuple(vals))
        rows=cur.fetchall(); cur.close(); put_conn(conn)
        data=[{
            "lesson_id":r[0],"learner_id":r[1],
            "understanding":r[2],"application":r[3],
            "communication":r[4],"behavior":r[5],
            "total":r[6],"timestamp":r[7].strftime("%Y-%m-%d %H:%M")
        } for r in rows]
        return jsonify(data)
    except Exception as e:
        logging.exception(e)
        return jsonify({"error":str(e)}),500


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    PORT=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=PORT)
