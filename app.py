import os, io, re, logging
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from psycopg2.pool import SimpleConnectionPool
from PyPDF2 import PdfReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from openai import OpenAI

# ------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://domain-lp-five.vercel.app"}})
logging.basicConfig(level=logging.INFO)

# Load environment variables
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DB_URL = os.getenv("DATABASE_URL")

if not OPENAI_KEY:
    logging.error("❌ Missing OPENAI_API_KEY — please set it in Railway environment variables.")
if not DB_URL:
    logging.warning("⚠️ No DATABASE_URL found — DB features disabled.")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_KEY)

# Optional DB connection pool
pool = SimpleConnectionPool(1, 10, dsn=DB_URL) if DB_URL else None


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def get_conn():
    """Get connection from pool (if available)."""
    if not pool:
        raise Exception("Database not configured.")
    return pool.getconn()

def put_conn(c):
    if pool:
        pool.putconn(c)

def extract_text_from_pdf(file):
    """Extracts up to 5000 characters of text from uploaded PDF."""
    try:
        reader = PdfReader(file)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        return text[:5000] if text.strip() else "PDF content extracted (empty)."
    except Exception as e:
        logging.error(f"PDF extraction failed: {e}")
        return "PDF uploaded (text extraction failed)."


# ------------------------------------------------------------
# LESSON PLAN GENERATOR
# ------------------------------------------------------------
def generate_lesson_plan_text(teacher, title, duration, cefr, profile, content):
    """Generate structured HTML lesson plan including domain checklists."""
    prompt = f"""
You are a senior English Language Teaching (ELT) instructional designer for BAE Systems.

Generate a professional, structured HTML lesson plan for classroom delivery using a formal instructional tone.

Requirements:
- Output valid HTML (no markdown, no code fences).
- Include ALL sections as shown below.

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
<li>At least 3 measurable objectives aligned with CEFR outcomes.</li>
</ul>

------------------------------------------------------------
<h3>2. Lesson Plan Structure</h3>
<table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#e0e7ff;font-weight:bold;text-align:left">
<th>Stage</th><th>Duration</th><th>Objective/Skill</th><th>Activities</th><th>Teacher Role</th><th>Learner Role</th><th>Materials</th>
</tr>
<tr><td>Warm-Up</td><td>5–10 min</td><td>Activate prior knowledge.</td><td>Quick discussion or brainstorming.</td><td>Facilitates, elicits responses.</td><td>Responds, shares ideas.</td><td>Board, visuals.</td></tr>
<tr><td>Presentation</td><td>10 min</td><td>Introduce target language.</td><td>Demonstrate grammar or vocabulary use in context.</td><td>Explains, models, checks understanding.</td><td>Listens and takes notes.</td><td>Projector, whiteboard.</td></tr>
<tr><td>Practice (Controlled)</td><td>10 min</td><td>Reinforce comprehension.</td><td>Pair or group structured exercises.</td><td>Monitors, corrects errors.</td><td>Completes tasks accurately.</td><td>Worksheets.</td></tr>
<tr><td>Production (Freer)</td><td>10 min</td><td>Apply language creatively.</td><td>Role-play or group presentation.</td><td>Guides, observes, supports.</td><td>Uses target language independently.</td><td>Real-life prompts.</td></tr>
<tr><td>Review & Wrap-Up</td><td>5 min</td><td>Summarize learning outcomes.</td><td>Class recap and reflection.</td><td>Summarizes key points.</td><td>Reflects, asks questions.</td><td>Notebook.</td></tr>
</table>

------------------------------------------------------------
<h3>3. Supporting Details</h3>
<p><b>Purpose:</b> Reinforce understanding and application of target skills in real contexts.</p>
<p><b>Method:</b> Communicative and task-based learning.</p>
<p><b>Expected Outcome:</b> Learners demonstrate measurable improvement in understanding and communication.</p>

------------------------------------------------------------
<h3>4. Performance Domain Checklists</h3>
<div style="background:#f9fafb;border-left:4px solid #2563eb;padding:10px;margin:10px 0;">
  <b>Each domain checklist</b> is rated <b>1–5</b> (5 = Excellent, 1 = Poor). Each domain totals <b>25 points</b>.
</div>

<p>Analyze the uploaded lesson content below and generate 5 measurable, 
lesson-specific indicators for each domain (Understanding, Application, Communication, Behavior). 
Make them directly relevant to the lesson content, not generic.</p>

Lesson content reference:
{content}

<h4 style="color:#2563eb">Understanding (U)</h4>
<ul>
<li>...</li>
<li>...</li>
</ul>

<h4 style="color:#16a34a">Application (A)</h4>
<ul>
<li>...</li>
<li>...</li>
</ul>

<h4 style="color:#f59e0b">Communication (C)</h4>
<ul>
<li>...</li>
<li>...</li>
</ul>

<h4 style="color:#dc2626">Behavior (B)</h4>
<ul>
<li>...</li>
<li>...</li>
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
------------------------------------------------------------
<h3>6. Reflection (Instructor Review)</h3>
<ul>
<!-- The model will generate three context-specific reflection questions below -->
</ul>

"""
    try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert ELT instructional designer working under BAE Systems standards. "
                    "Do not restate instructions or placeholders. "
                    "Only output fully populated HTML sections that match the requested structure."
                ),
            },
            {
                "role": "user",
                "content": f"Generate the following HTML structure exactly, filling all fields with relevant content derived from the uploaded lesson:\n\n{prompt}"
            },
        ],
    )

    html = response.choices[0].message.content.strip()
    html = re.sub(r"^```(?:html)?|```$", "", html, flags=re.MULTILINE).strip()
    html = html.replace("\\n", "\n").replace('\\"', '"')
    return html

except Exception as e:
    logging.error(f"AI generation failed: {e}")
    return f"<p style='color:red'>AI generation failed: {e}</p>"


        html = response.choices[0].message.content.strip()
        html = re.sub(r"^```(?:html)?|```$", "", html, flags=re.MULTILINE).strip()
        return html

    except Exception as e:
        logging.error(f"AI generation failed: {e}")
        return f"<p style='color:red'>AI generation failed: {e}</p>"


# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK", "message": "Lesson Planner Backend Active"})


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
            if file.filename.lower().endswith(".pdf"):
                content = extract_text_from_pdf(file)
            else:
                content = file.read().decode("utf-8", errors="ignore")

        html_output = generate_lesson_plan_text(teacher, title, duration, cefr, profile, content)
        return jsonify({"status": "success", "html": html_output})

    except Exception as e:
        logging.error(f"Error in /generate_lesson: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.post("/download_pdf")
def download_pdf():
    try:
        html_content = request.form.get("html", "")
        if not html_content:
            return jsonify({"error": "No HTML content provided"}), 400

        from reportlab.lib.units import inch
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch
        )
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
# MAIN (RAILWAY ENTRY)
# ------------------------------------------------------------
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
