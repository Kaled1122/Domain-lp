import os, logging, io
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from psycopg2.pool import SimpleConnectionPool
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from openai import OpenAI

# --- App setup ---
app = Flask(__name__)
CORS(app, origins="*")
logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Database ---
DB_URL = os.getenv("DATABASE_URL")
pool = SimpleConnectionPool(1, 10, dsn=DB_URL)

def get_conn(): return pool.getconn()
def put_conn(c): pool.putconn(c)

# --- Safe float ---
def safe_float(v):
    try: return float(v)
    except: return 0.0

def compute_total(u,a,c,b): return round(safe_float(u)+safe_float(a)+safe_float(c)+safe_float(b),2)

# --- Lesson generation ---
@app.post("/generate_lesson")
def generate_lesson():
    try:
        t=request.form.get; teacher=t("teacher",""); title=t("lesson_title","")
        dur=t("duration",""); cefr=t("cefr",""); prof=t("profile","")
        up=request.files.get("file"); content=up.read().decode("utf-8",errors="ignore") if up else ""
        prompt=f"""You are an ELT designer at BAE Systems KSA. Create a structured lesson plan...
Lesson Title:{title} Teacher:{teacher} Duration:{dur} CEFR:{cefr} Profile:{prof}
Source:{content}"""
        resp=client.chat.completions.create(model="gpt-4o-mini",temperature=0.4,
            messages=[{"role":"system","content":"Create measurable ELT lesson plans with crisp tables."},
                      {"role":"user","content":prompt}])
        return f"<html><body>{resp.choices[0].message.content.replace('\n','<br>')}</body></html>"
    except Exception as e:
        logging.exception(e)
        return f"<p>Error:{e}</p>",500

# --- Save performance ---
@app.post("/save_performance")
def save_perf():
    try:
        data=request.get_json(force=True)
        conn=get_conn(); cur=conn.cursor()
        for r in data:
            u,a,c,b=[safe_float(r.get(k)) for k in ("understanding","application","communication","behavior")]
            total=compute_total(u,a,c,b)
            cur.execute("""INSERT INTO performance_records
                (lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (r.get("lesson_id"),r.get("learner_id"),u,a,c,b,total,datetime.now()))
        conn.commit(); cur.close(); put_conn(conn)
        return jsonify({"message":f"{len(data)} records saved"})
    except Exception as e:
        logging.exception(e); return jsonify({"error":str(e)}),500

# --- Fetch data (with filters) ---
@app.get("/fetch_data")
def fetch_data():
    try:
        lid=request.args.get("learner_id","")
        fromd=request.args.get("from",""); tod=request.args.get("to","")
        q="SELECT lesson_id,learner_id,understanding,application,communication,behavior,total,timestamp FROM performance_records WHERE 1=1"
        vals=[]
        if lid: q+=" AND learner_id ILIKE %s"; vals.append(f"%{lid}%")
        if fromd: q+=" AND timestamp >= %s"; vals.append(fromd)
        if tod: q+=" AND timestamp <= %s"; vals.append(tod)
        q+=" ORDER BY timestamp DESC"
        conn=get_conn(); cur=conn.cursor(); cur.execute(q,tuple(vals)); rows=cur.fetchall()
        data=[{"lesson_id":r[0],"learner_id":r[1],"understanding":r[2],"application":r[3],
               "communication":r[4],"behavior":r[5],"total":r[6],"timestamp":r[7].strftime("%Y-%m-%d %H:%M")} for r in rows]
        cur.close(); put_conn(conn)
        return jsonify(data)
    except Exception as e:
        logging.exception(e); return jsonify({"error":str(e)}),500

# --- Export Excel ---
@app.get("/export_excel")
def export_excel():
    try:
        conn=get_conn()
        df=pd.read_sql("SELECT * FROM performance_records ORDER BY timestamp DESC",conn)
        put_conn(conn)
        output=io.BytesIO()
        df.to_excel(output,index=False)
        output.seek(0)
        return send_file(output,as_attachment=True,download_name="records.xlsx")
    except Exception as e:
        return jsonify({"error":str(e)}),500

# --- Export PDF ---
@app.get("/export_pdf")
def export_pdf():
    try:
        conn=get_conn()
        cur=conn.cursor(); cur.execute("SELECT learner_id,total,timestamp FROM performance_records ORDER BY timestamp DESC LIMIT 100")
        rows=cur.fetchall(); cur.close(); put_conn(conn)
        buf=io.BytesIO()
        doc=SimpleDocTemplate(buf,pagesize=A4)
        styles=getSampleStyleSheet()
        data=[["Learner","Total","Date"]]+[[r[0],r[1],r[2].strftime("%Y-%m-%d")] for r in rows]
        elems=[Paragraph("Performance Report",styles["Title"]),Spacer(1,12),Table(data)]
        doc.build(elems)
        buf.seek(0)
        return send_file(buf,as_attachment=True,download_name="report.pdf")
    except Exception as e:
        return jsonify({"error":str(e)}),500

# --- Backup (CSV) ---
@app.get("/backup_db")
def backup_db():
    conn=get_conn()
    df=pd.read_sql("SELECT * FROM performance_records",conn)
    put_conn(conn)
    path="/tmp/backup.csv"
    df.to_csv(path,index=False)
    return send_file(path,as_attachment=True)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",8080)))
