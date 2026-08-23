from flask import Flask, render_template, send_file
import sqlite3
import math
import json
from database.db import create_tables, get_bin_locations

app = Flask(__name__)

DB_PATH = "database/db.sqlite3"

# Ensure schema and seed data exist before the first request is served
create_tables()

# Single source of truth — coordinates loaded from bin_master, not hardcoded
BIN_LOCATIONS = get_bin_locations()

# Fixed depot coordinate (collection facility / starting point for all routes)
DEPOT = (6.895, 79.840)


# ---------------------------------------------------------------------------
# DATABASE HELPER
# ---------------------------------------------------------------------------

def get_data():
    """Return all telemetry readings ordered by most recent timestamp first."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bin_id, fill_level, timestamp
        FROM telemetry
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# ROUTING ALGORITHMS (module-scope — shared by analytics and map views)
# ---------------------------------------------------------------------------

def haversine(a, b):
    """
    Haversine formula: returns the great-circle distance in km
    between two points given as (latitude, longitude) tuples.
    """
    R = 6371
    lat1, lon1 = a
    lat2, lon2 = b
    phi1    = math.radians(lat1)
    phi2    = math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    x = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def nearest_neighbour_route(locations):
    """
    Nearest-Neighbour TSP heuristic.
    Builds a route that starts at DEPOT, visits every location in `locations`
    by always travelling to the closest unvisited point, then returns to DEPOT.

    Parameters
    ----------
    locations : list of (lat, lon) tuples

    Returns
    -------
    route          : list of [lat, lon] pairs (Leaflet-compatible)
    total_distance : float, total route length in km (rounded to 2 d.p.)
    """
    if not locations:
        return [], 0.0

    unvisited  = list(locations)
    current    = DEPOT
    route      = [list(DEPOT)]
    total_dist = 0.0

    while unvisited:
        nearest = min(unvisited, key=lambda p: haversine(current, p))
        total_dist += haversine(current, nearest)
        route.append(list(nearest))
        unvisited.remove(nearest)
        current = nearest

    # Return leg: last visited bin back to depot
    total_dist += haversine(current, DEPOT)
    route.append(list(DEPOT))

    return route, round(total_dist, 2)


def calculate_route_distances(latest_bins):
    """
    Computes real Haversine-based distances for both the traditional and
    the optimised (DSS) collection routes.

    traditional_distance : nearest-neighbour route visiting ALL bins,
                           depot → all bins → depot
    optimized_distance   : nearest-neighbour route visiting ONLY critical
                           bins (fill_level >= 80%), depot → critical → depot

    Returns
    -------
    (traditional_distance, optimized_distance) in km, both rounded to 2 d.p.
    """
    all_coords = [
        BIN_LOCATIONS[row[0]]
        for row in latest_bins.values()
        if row[0] in BIN_LOCATIONS
    ]
    critical_coords = [
        BIN_LOCATIONS[row[0]]
        for row in latest_bins.values()
        if row[0] in BIN_LOCATIONS and row[1] >= 80
    ]

    _, traditional_distance = nearest_neighbour_route(all_coords)
    _, optimized_distance   = nearest_neighbour_route(critical_coords)

    return traditional_distance, optimized_distance


# ---------------------------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    data = get_data()

    # Keep only the most recent reading per bin
    latest_bins = {}
    for row in data:
        if row[0] not in latest_bins:
            latest_bins[row[0]] = row

    alerts         = []
    total_fill     = 0
    critical_count = 0

    for row in latest_bins.values():
        fill_level  = row[1]
        total_fill += fill_level

        if fill_level >= 80:
            critical_count += 1
            alerts.append(f"⚠ {row[0]} is critically full ({fill_level}%)")

    total_bins   = len(latest_bins)
    average_fill = round(total_fill / total_bins, 1) if total_bins > 0 else 0

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

    # Keep only the most recent reading per bin
    latest_bins = {}
    for row in data:
        if row[0] not in latest_bins:
            latest_bins[row[0]] = row

    chart_labels = [row[0] for row in latest_bins.values()]
    chart_values = [row[1] for row in latest_bins.values()]

    total_bins    = len(chart_values)
    critical_bins = sum(1 for v in chart_values if v >= 80)

    # -----------------------------------------------------------------------
    # Real Haversine-based efficiency calculation (not a fabricated formula)
    # -----------------------------------------------------------------------
    traditional_distance, optimized_distance = calculate_route_distances(latest_bins)

    if traditional_distance > 0:
        efficiency = round(
            ((traditional_distance - optimized_distance) / traditional_distance) * 100
        )
    else:
        efficiency = 0

    # DSS recommendation text
    if critical_bins == 0:
        recommendation = "All bins are currently operating within safe levels."
    elif critical_bins <= 2:
        recommendation = "Selective smart collection is recommended for critical bins."
    else:
        recommendation = "Multiple critical bins detected. Immediate optimised collection required."

    # Risk index
    risk_score = round((critical_bins / total_bins) * 100) if total_bins > 0 else 0

    if risk_score == 0:
        system_state = "OPTIMAL"
    elif risk_score <= 20:
        system_state = "LOW RISK"
    elif risk_score <= 50:
        system_state = "MEDIUM RISK"
    else:
        system_state = "HIGH RISK"

    # Historical risk trend (last 20 telemetry readings, oldest first)
    risk_history = []
    risk_labels  = []
    for row in reversed(data[:20]):
        risk_history.append(row[1])
        risk_labels.append(row[2])

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


@app.route("/generate-report")
def generate_report():
    from reports.report_generator import create_pdf_report
    pdf_path = create_pdf_report()
    return send_file(pdf_path, as_attachment=True)


@app.route("/routes")
def routes():
    data = get_data()

    # Keep only the most recent reading per bin
    latest_bins = {}
    for row in data:
        if row[0] not in latest_bins:
            latest_bins[row[0]] = row

    # Filter to critical bins only; sort highest fill level first
    priority_bins = [
        {"bin_id": row[0], "fill_level": row[1], "timestamp": row[2]}
        for row in latest_bins.values()
        if row[1] >= 80
    ]
    priority_bins.sort(key=lambda x: x["fill_level"], reverse=True)

    return render_template("routes.html", priority_bins=priority_bins)


@app.route("/map")
def map_view():
    data = get_data()

    # Keep only the most recent reading per bin
    latest_bins = {}
    for row in data:
        if row[0] not in latest_bins:
            latest_bins[row[0]] = row

    bins_data     = []
    critical_bins = []

    for row in latest_bins.values():
        bin_id     = row[0]
        fill_level = row[1]

        if bin_id not in BIN_LOCATIONS:
            continue

        lat, lon = BIN_LOCATIONS[bin_id]
        bins_data.append({"id": bin_id, "fill": fill_level, "lat": lat, "lon": lon})

        if fill_level >= 80:
            critical_bins.append((lat, lon))

    route          = []
    total_distance = 0
    estimated_time = 0

    if len(critical_bins) >= 1:
        route, total_distance = nearest_neighbour_route(critical_bins)
        estimated_time        = round((total_distance / 25) * 60, 1)

    return render_template(
        "map.html",
        bins=json.dumps(bins_data),
        route=json.dumps(route),
        depot=json.dumps(list(DEPOT)),
        total_distance=total_distance,
        estimated_time=estimated_time
    )


if __name__ == "__main__":
    app.run(debug=True)
