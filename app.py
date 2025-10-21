import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# --------------------- DATABASE CONNECTION ---------------------
DB_URL = "postgresql://postgres:eoTlRaNGAiMEqwzsYPkzKJYWudCSRSOq@postgres.railway.internal:5432/railway"

def get_db():
    return psycopg2.connect(DB_URL, sslmode="require")

def init_db():
    conn = get_db()
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
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --------------------- HELPER FUNCTIONS ---------------------
def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def compute_total(u, a, c, b):
    return round(safe_float(u) + safe_float(a) + safe_float(c) + safe_float(b), 2)

# --------------------- SAVE PERFORMANCE ---------------------
@app.route("/save_performance", methods=["POST"])
def save_performance():
    try:
        data = request.get_json(force=True)
        if not isinstance(data, list):
            return jsonify({"error": "Expected a list of performance records"}), 400

        conn = get_db()
        cur = conn.cursor()

        for r in data:
            u = safe_float(r.get("understanding"))
            a = safe_float(r.get("application"))
            c = safe_float(r.get("communication"))
            b = safe_float(r.get("behavior"))
            total = compute_total(u, a, c, b)

            cur.execute("""
                INSERT INTO performance_records
                (lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                (r.get("lesson_id") or "").strip(),
                (r.get("learner_id") or "").strip(),
                u, a, c, b, total, datetime.now()
            ))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": f"{len(data)} records saved successfully."})

    except Exception as e:
        print("❌ save_performance error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- FETCH ALL DATA ---------------------
@app.route("/fetch_data", methods=["GET"])
def fetch_data():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, lesson_id, learner_id, understanding, application, communication, behavior, total, timestamp
            FROM performance_records
            ORDER BY timestamp DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = [{
            "record_id": r[0],
            "lesson_id": r[1],
            "learner_id": r[2] or "",
            "understanding": r[3] or 0,
            "application": r[4] or 0,
            "communication": r[5] or 0,
            "behavior": r[6] or 0,
            "total": r[7] or compute_total(r[3], r[4], r[5], r[6]),  # ✅ guaranteed
            "timestamp": r[8].strftime("%Y-%m-%d %H:%M")
        } for r in rows]

        return jsonify(data)
    except Exception as e:
        print("❌ fetch_data error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- FETCH AVERAGES ---------------------
@app.route("/fetch_averages", methods=["GET"])
def fetch_averages():
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
        WITH clean AS (
            SELECT LOWER(TRIM(learner_id)) AS lid,
                   COALESCE(understanding,0) AS u,
                   COALESCE(application,0) AS a,
                   COALESCE(communication,0) AS c,
                   COALESCE(behavior,0) AS b
            FROM performance_records
            WHERE TRIM(COALESCE(learner_id,'')) <> ''
        )
        SELECT
            lid AS learner_id,
            ROUND(AVG(u), 2) AS understanding,
            ROUND(AVG(a), 2) AS application,
            ROUND(AVG(c), 2) AS communication,
            ROUND(AVG(b), 2) AS behavior,
            ROUND(AVG(u)+AVG(a)+AVG(c)+AVG(b), 2) AS total,
            COUNT(*) AS entries
        FROM clean
        GROUP BY lid
        ORDER BY lid;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = [{
            "learner_id": r[0],
            "understanding": r[1],
            "application": r[2],
            "communication": r[3],
            "behavior": r[4],
            "total": r[5],   # ✅ always defined
            "entries": r[6]
        } for r in rows]

        return jsonify(data)

    except Exception as e:
        print("❌ fetch_averages error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- REPAIR TOTALS ---------------------
@app.route("/recalculate_totals", methods=["POST"])
def recalc_totals():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        UPDATE performance_records
        SET total = COALESCE(understanding,0) + COALESCE(application,0) +
                    COALESCE(communication,0) + COALESCE(behavior,0)
        WHERE total IS NULL;
        """)
        updated = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": f"Recalculated totals for {updated} rows."})
    except Exception as e:
        print("❌ recalc_totals error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------- MAIN ---------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
