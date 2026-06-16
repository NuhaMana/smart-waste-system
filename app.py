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

        if bin_id not in latest_bins:
            latest_bins[bin_id] = row

    chart_labels = []
    chart_values = []

    for row in latest_bins.values():
        chart_labels.append(row[0])
        chart_values.append(row[1])

    total_bins = len(chart_values)

    critical_bins = 0

    for value in chart_values:
        if value >= 80:
            critical_bins += 1

    traditional_distance = total_bins * 2
    optimized_distance = max(2, critical_bins * 2)

    efficiency = round(
        ((traditional_distance - optimized_distance)
        / traditional_distance) * 100
    )

    if critical_bins == 0:
        recommendation = "All bins are currently operating within safe levels."

    elif critical_bins <= 2:
        recommendation = "Selective smart collection is recommended for critical bins."

    else:
        recommendation = "Multiple critical bins detected. Immediate optimized collection required."

    # =========================
    # SMART RISK SCORE (FIXED)
    # =========================

    risk_score = round((critical_bins / total_bins) * 100) if total_bins > 0 else 0

    if risk_score == 0:
        system_state = "OPTIMAL"
    elif risk_score <= 20:
        system_state = "LOW RISK"
    elif risk_score <= 50:
        system_state = "MEDIUM RISK"
    else:
        system_state = "HIGH RISK"
    
        # =========================
    # REAL HISTORICAL RISK TREND
    # =========================

    risk_history = []
    risk_labels = []

    historical_data = data[:20]

    for row in reversed(historical_data):

        timestamp = row[2]
        fill_level = row[1]

        risk_history.append(fill_level)

        risk_labels.append(timestamp)

    return render_template(
        "analytics.html",
        labels=chart_labels,
        values=chart_values,
        critical_bins=critical_bins,
        efficiency=efficiency,
        recommendation=recommendation,
        traditional_distance=traditional_distance,
        optimized_distance=optimized_distance,
        risk_score=risk_score,
        system_state=system_state,
        risk_history=risk_history,
        risk_labels=risk_labels
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
    import json

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

        if bin_id not in latest_bins:
            latest_bins[bin_id] = row


    BIN_LOCATIONS = {
        "BIN-001": (6.900, 79.850),
        "BIN-002": (6.905, 79.860),
        "BIN-003": (6.910, 79.870),
        "BIN-004": (6.915, 79.880),
        "BIN-005": (6.920, 79.890),
    }

    bins_data = []

    critical_bins = []

    for row in latest_bins.values():

        bin_id = row[0]
        fill_level = row[1]

        if bin_id not in BIN_LOCATIONS:
            continue

        lat, lon = BIN_LOCATIONS[bin_id]

        bins_data.append({
            "id": bin_id,
            "fill": fill_level,
            "lat": lat,
            "lon": lon
        })

        if fill_level >= 80:
            critical_bins.append([lat, lon])

    route = []

    if len(critical_bins) >= 2:

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

        total_distance = 0

        for i in range(len(route)-1):
            total_distance += haversine(
                route[i],
                route[i+1]
            )

        estimated_time = (total_distance / 25) * 60
        total_distance = round(total_distance, 2)
        estimated_time = round(estimated_time, 1)

        print("Route Distance:", round(total_distance, 2), "km")
        print("Estimated Time:", round(estimated_time, 1), "minutes")

    return render_template(
        "map.html",
        bins=json.dumps(bins_data),
        route=json.dumps(route),
        total_distance=total_distance if route else 0,
        estimated_time=estimated_time if route else 0
    )
        
    
if __name__ == "__main__":
    app.run(debug=True)


