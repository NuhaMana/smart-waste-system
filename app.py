from flask import Flask, render_template
import sqlite3

app = Flask(__name__)

DB_PATH = "database/db.sqlite3"

def get_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT bin_id, fill_level, timestamp
        FROM bins
        ORDER BY timestamp DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows


@app.route("/")
def index():
    data = get_data()
    return render_template("index.html", data=data)


if __name__ == "__main__":
    app.run(debug=True)