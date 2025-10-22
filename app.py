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


def generate_lesson_plan_text(teacher, title, duration, cefr, profile, content):
    """Generate structured HTML lesson plan."""
    if not client:
        return "AI client not configured."

    system_prompt = (
        "You are an expert English Language Teaching (ELT) planner. "
        "Generate a professional, classroom-ready lesson plan in pure HTML (no markdown, no JSON). "
        "Include: Title, Teacher, Duration, CEFR Level, Learner Profile, "
        "Lesson Objectives, Lesson Plan Structure (Warm-up / Practice / Production), "
        "Supporting Details, and Reflection. Avoid rubrics or evaluation language."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"""
Teacher: {teacher}
Lesson Title: {title}
Duration: {duration}
CEFR Level: {cefr}
Learner Profile: {profile}
Lesson Content: {content}
""",
                },
            ],
        )
        html = response.choices[0].message.content.strip()

        # --- Clean output (handle JSON or code fences) ---
        if html.startswith("{") and "html" in html:
            try:
                html = json.loads(html)["html"]
            except Exception:
                pass
        html = re.sub(r"^```(?:html)?|```$", "", html, flags=re.MULTILINE).strip()
        html = html.replace("\\n", "\n").replace('\\"', '"')
        return html

    except Exception as e:
        logging.error(f"AI generation failed: {e}")
        return f"<p style='color:red'>AI generation failed: {e}</p>"


def create_pdf_from_html(html_content):
    """Converts HTML-like text into a simple PDF using reportlab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Lesson Plan", styles["Title"]),
        Spacer(1, 12),
        Paragraph(html_content.replace("\n", "<br/>"), styles["BodyText"]),
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer


# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK", "message": "Domain Lesson Planner Backend Active"})


@app.post("/generate_lesson")
def generate_lesson():
    """Generates a lesson plan via OpenAI and returns HTML."""
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
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lessons (
                        id SERIAL PRIMARY KEY,
                        teacher TEXT,
                        title TEXT,
                        cefr TEXT,
                        profile TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        html TEXT
                    );
                    """
                )
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
        pdf_buffer = create_pdf_from_html(html_content)
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"lesson_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        )
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------
# PERFORMANCE REGISTER ROUTES
# ------------------------------------------------------------
@app.post("/save_performance")
def save_perf():
    """Save performance records to DB."""
    if not pool:
        return jsonify({"error": "Database not configured."}), 503
    try:
        data = request.get_json(force=True)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
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
            """
        )
        for r in data:
            lid = r.get("lesson_id")
            rid = r.get("learner_id")
            if not lid or not rid:
                continue
            u, a, c, b = [safe_float(r.get(k)) for k in ("understanding", "application", "communication", "behavior")]
            total = compute_total(u, a, c, b)
            cur.execute(
                "INSERT INTO performance_records (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (lid, rid, u, a, c, b, total, datetime.now()),
            )
        conn.commit()
        cur.close()
        put_conn(conn)
        return jsonify({"message": f"{len(data)} records saved successfully."})
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500


@app.get("/fetch_data")
def fetch_data():
    """Fetch performance data with filters."""
    if not pool:
        return jsonify({"error": "Database not configured."}), 503
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
        q += " ORDER BY timestamp DESC LIMIT 1000"
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(q, tuple(vals))
        rows = cur.fetchall()
        cur.close()
        put_conn(conn)
        data = [
            {
                "lesson_id": r[0],
                "learner_id": r[1],
                "understanding": r[2],
                "application": r[3],
                "communication": r[4],
                "behavior": r[5],
                "total": r[6],
                "timestamp": r[7].strftime("%Y-%m-%d %H:%M"),
            }
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        logging.exception(e)
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------
# MAIN ENTRY
# ------------------------------------------------------------
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
