from flask import Flask, render_template
import sqlite3
import folium

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

    alerts = []

    latest_bins = {}

    # Keep latest entry per bin
    for row in data:

        bin_id = row[0]

        if bin_id not in latest_bins:
            latest_bins[bin_id] = row

    # Generate alerts
    for row in latest_bins.values():

        fill_level = row[1]

        if fill_level >= 80:

            alerts.append({
                "bin_id": row[0],
                "fill_level": fill_level
            })

    return render_template(
        "dashboard.html",
        data=data,
        alerts=alerts
    )


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

    data = get_data()

    latest_bins = {}

    # Keep latest entry per bin
    for row in data:
        bin_id = row[0]

        if bin_id not in latest_bins:
            latest_bins[bin_id] = row

    priority_bins = []

    for row in latest_bins.values():

        fill_level = row[1]

        if fill_level >= 80:

            priority_bins.append({
                "bin_id": row[0],
                "fill_level": fill_level,
                "timestamp": row[2]
            })

    # Highest fill level first
    priority_bins.sort(
        key=lambda x: x["fill_level"],
        reverse=True
    )

    return render_template(
        "routes.html",
        priority_bins=priority_bins
    )

@app.route("/map")
def map_view():

    data = get_data()

    latest_bins = {}

    for row in data:
        bin_id = row[0]
        latest_bins[bin_id] = row

    m = folium.Map(location=[6.9, 79.9], zoom_start=12)

    high_priority_locations = []

    for row in latest_bins.values():

        bin_id = row[0]
        fill_level = row[1]

        lat = 6.9 + (hash(bin_id) % 100) * 0.001
        lon = 79.9 + (hash(bin_id) % 100) * 0.001

        if fill_level >= 80:
            color = "red"

            high_priority_locations.append([lat, lon])

        elif fill_level >= 50:
            color = "orange"

        else:
            color = "green"

        folium.Marker(
            location=[lat, lon],
            popup=f"{bin_id} - {fill_level}%",
            icon=folium.Icon(color=color)
        ).add_to(m)

    # Draw smart collection route
    if len(high_priority_locations) > 1:

        folium.PolyLine(
            high_priority_locations,
            color="blue",
            weight=4,
            opacity=0.8
        ).add_to(m)

    return m._repr_html_()

if __name__ == "__main__":
    app.run(debug=True)


