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
def dashboard():
    data = get_data()
    return render_template("dashboard.html", data=data)


@app.route("/analytics")
def analytics():

    data = get_data()

    latest_bins = {}

    for row in data:
        bin_id = row[0]

        # keep only latest entry per bin
        if bin_id not in latest_bins:
            latest_bins[bin_id] = row

    chart_labels = []
    chart_values = []

    for row in latest_bins.values():
        chart_labels.append(row[0])
        chart_values.append(row[1])

    return render_template(
        "analytics.html",
        labels=chart_labels,
        values=chart_values
    )

@app.route("/routes")
def routes():
    return render_template("routes.html")


if __name__ == "__main__":
    app.run(debug=True)