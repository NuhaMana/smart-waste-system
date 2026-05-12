from flask import Flask, render_template
import sqlite3
import folium
BIN_LOCATIONS = {
    "BIN-001": (6.900, 79.850),
    "BIN-002": (6.905, 79.860),
    "BIN-003": (6.910, 79.870),
    "BIN-004": (6.915, 79.880),
    "BIN-005": (6.920, 79.890),
}

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

    latest_bins = {}

    for row in data:
        bin_id = row[0]

        if bin_id not in latest_bins:
            latest_bins[bin_id] = row

    alerts = []

    total_fill = 0
    critical_count = 0

    for row in latest_bins.values():

        fill_level = row[1]

        total_fill += fill_level

        if fill_level >= 80:

            critical_count += 1

            alerts.append(
                f"⚠ {row[0]} is critically full ({fill_level}%)"
            )

    total_bins = len(latest_bins)

    average_fill = 0

    if total_bins > 0:
        average_fill = round(total_fill / total_bins, 1)

        
    return render_template(
        "dashboard.html",
        data=data,
        alerts=alerts,
        total_bins=total_bins,
        critical_count=critical_count,
        average_fill=average_fill    
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

    import math
    from folium import Element

    def haversine(a, b):
        R = 6371

        lat1, lon1 = a
        lat2, lon2 = b

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)

        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        x = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2

        return 2 * R * math.atan2(math.sqrt(x), math.sqrt(1-x))


    data = get_data()

    latest_bins = {}

    for row in data:
        bin_id = row[0]
        latest_bins[bin_id] = row

    m = folium.Map(location=[6.905, 79.865], zoom_start=14)

    BIN_LOCATIONS = {
        "BIN-001": (6.900, 79.850),
        "BIN-002": (6.905, 79.860),
        "BIN-003": (6.910, 79.870),
        "BIN-004": (6.915, 79.880),
        "BIN-005": (6.920, 79.890),
    }

    critical_bins = []

    # MARKERS
    for row in latest_bins.values():

        bin_id = row[0]
        fill_level = row[1]

        if bin_id not in BIN_LOCATIONS:
            continue

        lat, lon = BIN_LOCATIONS[bin_id]

        if fill_level >= 80:
            color = "red"
            critical_bins.append([lat, lon])
        elif fill_level >= 50:
            color = "orange"
        else:
            color = "green"

        folium.Marker(
            location=[lat, lon],
            popup=f"{bin_id} - {fill_level}%",
            icon=folium.Icon(color=color)
        ).add_to(m)

    # ROUTE OPTIMIZATION
    if len(critical_bins) >= 2:

        route = []

        current = critical_bins.pop(0)
        route.append(current)

        while critical_bins:

            next_bin = min(
                critical_bins,
                key=lambda x: haversine(current, x)
            )

            route.append(next_bin)
            critical_bins.remove(next_bin)
            current = next_bin

        # Distance + time calculation
        total_distance = 0

        for i in range(len(route)-1):
            total_distance += haversine(route[i], route[i+1])

        estimated_time = (total_distance / 25) * 60

        print("Route Distance:", round(total_distance, 2), "km")
        print("Estimated Time:", round(estimated_time, 1), "minutes")

        # Draw route
        folium.PolyLine(
            locations=route,
            color="blue",
            weight=5,
            opacity=0.8
        ).add_to(m)

    return m._repr_html_()
if __name__ == "__main__":
    app.run(debug=True)


