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
CORS(app, resources={r"/*": {"origins": "https://domain-lp-five.vercel.app"}})
logging.basicConfig(level=logging.INFO)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DB_URL = os.getenv("DATABASE_URL")

if not OPENAI_KEY:
    logging.warning("⚠️ Missing OPENAI_API_KEY — AI generation will fail.")
if not DB_URL:
    logging.warning("⚠️ Missing DATABASE_URL — Database functions will fail.")

# Initialize components
client = OpenAI(api_key=OPENAI_KEY or "dummy_key")
pool = SimpleConnectionPool(1, 10, dsn=DB_URL) if DB_URL else None


# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------
def get_conn():
    if not pool:
        raise Exception("Database not configured.")
    return pool.getconn()


def put_conn(c):
    if pool:
        pool.putconn(c)


def safe_float(v):
    """Safely converts input to float, defaults to 0.0 on failure."""
    try:
        return float(v)
    except:
        return 0.0


def compute_total(u, a, c, b):
    """Computes the total score from four domain scores."""
    return round(safe_float(u) + safe_float(a) + safe_float(c) + safe_float(b), 2)


def extract_text_from_pdf(file):
    """Extracts text from a PDF file, truncating to 5000 characters."""
    try:
        reader = PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])[:5000]
    except Exception as e:
        logging.error(f"PDF extraction failed: {e}")
        return "PDF uploaded (text extraction failed)."


def generate_lesson_plan_text(teacher, title, duration, cefr, profile, content):
    """Generate structured HTML-based lesson plan using OpenAI GPT."""
    if not client:
        return "AI client not configured."

    system_prompt = (
        "You are an expert English Language Teaching (ELT) planner. "
        "Generate a structured, classroom-ready lesson plan in clean HTML. "
        "The output must include Title, Teacher, Duration, CEFR Level, Learner Profile, "
        "Lesson Objectives, Lesson Plan Structure (Warm-up / Practice / Production), "
        "Supporting Details, and Reflection. Avoid mentioning StanEval or evaluation rubrics."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"""
Teacher: {teacher}
Lesson Title: {title}
Duration: {duration} minutes
CEFR Level: {cefr}
Learner Profile: {profile}
Lesson Content: {content}
""",
                },
            ],
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"AI generation failed: {e}")
        return f"AI generation failed: {str(e)}"


def create_pdf_from_html(html_content):
    """Converts HTML-like text into a simple PDF using reportlab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Lesson Plan", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(html_content.replace("\n", "<br/>"), styles["BodyText"]))
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
    try:
        f = request.form
        teacher = f.get("teacher", "")
        title = f.get("lesson_title", "")
        duration = f.get("duration", "")
        cefr = f.get("cefr", "")
        profile = f.get("profile", "")
        file = request.files.get("file")

        # Extract text from uploaded file
        content = ""
        if file:
            if file.filename.endswith(".pdf"):
                content = extract_text_from_pdf(file)
            else:
                content = file.read().decode("utf-8", errors="ignore")

        # Generate lesson HTML using OpenAI
        html_output = generate_lesson_plan_text(
            teacher, title, duration, cefr, profile, content
        )

        # Save to DB if available
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
                    """
                    INSERT INTO lessons (teacher, title, cefr, profile, html)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (teacher, title, cefr, profile, html_output),
                )
                conn.commit()
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
# APP LAUNCHER (for Render)
# ------------------------------------------------------------
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
