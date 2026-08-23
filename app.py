from flask import Flask, render_template, send_file, jsonify
import sqlite3
import math
import json
from database.db import create_tables, get_bin_locations, get_bin_capacities

app = Flask(__name__)

DB_PATH = "database/db.sqlite3"

# Ensure schema and seed data exist before the first request is served
create_tables()

# Single source of truth — all metadata loaded from bin_master, never hardcoded
BIN_LOCATIONS  = get_bin_locations()   # {bin_id: (lat, lon)}
BIN_CAPACITIES = get_bin_capacities()  # {bin_id: capacity_litres}  — Missing 1

# Fixed depot coordinate (collection facility / route start and end point)
DEPOT = (6.895, 79.840)

# FIX 6: derived from the database — automatically correct if bins are added/removed
FIXED_BIN_ORDER = sorted(BIN_LOCATIONS.keys())


# ---------------------------------------------------------------------------
# DATABASE HELPER
# ---------------------------------------------------------------------------

def get_data():
    """Return all telemetry readings, most recent first. Returns [] on error."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT bin_id, fill_level, timestamp
            FROM telemetry
            ORDER BY timestamp DESC
        """)
        return cursor.fetchall()
    except sqlite3.Error as e:
        app.logger.error(f"get_data DB error: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# ROUTING & DISTANCE FUNCTIONS (module-scope — shared by all routes)
# ---------------------------------------------------------------------------

def haversine(a, b):
    """
    Haversine formula: great-circle distance in km between
    two (latitude, longitude) coordinate pairs.
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
    Route starts at DEPOT, visits all locations by choosing the closest
    unvisited point at each step, then returns to DEPOT.

    Returns: (route as list of [lat, lon] pairs, total distance in km)
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


def sequential_route_distance():
    """
    Fixed sequential baseline route: DEPOT → BIN-001 → … → BIN-00N → DEPOT.
    Represents a driver following a fixed paper schedule with no DSS.
    Used as the 'traditional' benchmark in efficiency calculations.
    """
    points = [BIN_LOCATIONS[b] for b in FIXED_BIN_ORDER if b in BIN_LOCATIONS]
    if not points:
        return 0.0
    total_dist = haversine(DEPOT, points[0])
    for i in range(len(points) - 1):
        total_dist += haversine(points[i], points[i + 1])
    total_dist += haversine(points[-1], DEPOT)
    return round(total_dist, 2)


def calculate_route_distances(latest_bins):
    """
    Returns:
      traditional_distance — fixed sequential route visiting ALL bins (no DSS)
      optimized_distance   — nearest-neighbour visiting ONLY critical bins (≥80%)
    Both distances include depot start and return legs.
    """
    traditional_distance = sequential_route_distance()
    critical_coords = [
        BIN_LOCATIONS[row[0]]
        for row in latest_bins.values()
        if row[0] in BIN_LOCATIONS and row[1] >= 80
    ]
    _, optimized_distance = nearest_neighbour_route(critical_coords)
    return traditional_distance, optimized_distance


# ---------------------------------------------------------------------------
# SHARED HELPERS
# ---------------------------------------------------------------------------

def _build_latest_bins(data):
    """Return {bin_id: row} keeping only the most recent reading per bin."""
    latest = {}
    for row in data:
        if row[0] not in latest:
            latest[row[0]] = row
    return latest


def _compute_volume(bin_id, fill_level):
    """
    Missing 1: Calculate actual waste volume in litres.
    volume = fill_level (%) / 100 × capacity_litres
    """
    capacity = BIN_CAPACITIES.get(bin_id, 120)
    return round(fill_level / 100 * capacity, 1)


# ---------------------------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    try:
        data        = get_data()
        latest_bins = _build_latest_bins(data)

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
            data=data[:50],              # FIX 5: cap server-side render at 50 rows
            alerts=alerts,
            total_bins=total_bins,
            critical_count=critical_count,
            average_fill=average_fill,
            capacities=BIN_CAPACITIES    # Missing 1: passed for volume column
        )
    except Exception as e:
        app.logger.error(f"dashboard error: {e}")
        return render_template(
            "dashboard.html",
            data=[], alerts=[], total_bins=0,
            critical_count=0, average_fill=0, capacities={}
        )


@app.route("/api/dashboard")
def api_dashboard():
    """
    JSON endpoint polled by the dashboard JavaScript every 10 seconds.
    Returns KPI figures, alerts, and the latest 50 readings with volumes.
    """
    try:
        data        = get_data()
        latest_bins = _build_latest_bins(data)

        alerts         = []
        total_fill     = 0
        critical_count = 0

        for row in latest_bins.values():
            fill_level  = row[1]
            total_fill += fill_level
            if fill_level >= 80:
                critical_count += 1
                alerts.append(f"{row[0]} is critically full ({fill_level}%)")

        total_bins   = len(latest_bins)
        average_fill = round(total_fill / total_bins, 1) if total_bins > 0 else 0

        readings = []
        for row in data[:50]:
            fl     = row[1]
            status = "HIGH" if fl >= 80 else ("MEDIUM" if fl >= 50 else "LOW")
            readings.append({
                "bin_id":        row[0],
                "fill_level":    fl,
                "volume_litres": _compute_volume(row[0], fl),   # Missing 1
                "status":        status,
                "timestamp":     row[2]
            })

        return jsonify({
            "total_bins":     total_bins,
            "critical_count": critical_count,
            "average_fill":   average_fill,
            "alerts":         alerts,
            "readings":       readings
        })
    except Exception as e:
        app.logger.error(f"api_dashboard error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/analytics")
def analytics():
    try:
        data        = get_data()
        latest_bins = _build_latest_bins(data)

        chart_labels  = [row[0] for row in latest_bins.values()]
        chart_values  = [row[1] for row in latest_bins.values()]
        total_bins    = len(chart_values)
        critical_bins = sum(1 for v in chart_values if v >= 80)

        traditional_distance, optimized_distance = calculate_route_distances(latest_bins)

        # FIX 2: when no bins need collection, efficiency is 0 — not 100%
        if traditional_distance > 0 and critical_bins > 0:
            efficiency = round(
                ((traditional_distance - optimized_distance) / traditional_distance) * 100
            )
        else:
            efficiency = 0

        if critical_bins == 0:
            recommendation = "All bins are currently operating within safe levels."
        elif critical_bins <= 2:
            recommendation = "Selective smart collection is recommended for critical bins."
        else:
            recommendation = "Multiple critical bins detected. Immediate optimised collection required."

        risk_score = round((critical_bins / total_bins) * 100) if total_bins > 0 else 0

        if risk_score == 0:
            system_state = "OPTIMAL"
        elif risk_score <= 20:
            system_state = "LOW RISK"
        elif risk_score <= 50:
            system_state = "MEDIUM RISK"
        else:
            system_state = "HIGH RISK"

        risk_history = []
        risk_labels  = []
        for row in reversed(data[:20]):
            risk_history.append(row[1])
            risk_labels.append(row[2])

        # Missing 1: actual waste volume across the network
        total_volume   = sum(_compute_volume(row[0], row[1]) for row in latest_bins.values())
        total_capacity = sum(BIN_CAPACITIES.get(row[0], 120) for row in latest_bins.values())
        network_capacity_pct = round((total_volume / total_capacity * 100), 1) if total_capacity > 0 else 0

        return render_template(
            "analytics.html",
            labels=chart_labels,
            values=chart_values,
            critical_bins=critical_bins,
            efficiency=efficiency,
            recommendation=recommendation,        # FIX 1: now passed correctly to template
            traditional_distance=traditional_distance,
            optimized_distance=optimized_distance,
            risk_score=risk_score,
            system_state=system_state,
            risk_history=risk_history,
            risk_labels=risk_labels,
            total_volume=total_volume,            # Missing 1
            total_capacity=total_capacity,        # Missing 1
            network_capacity_pct=network_capacity_pct  # Missing 1
        )
    except Exception as e:
        app.logger.error(f"analytics error: {e}")
        return f"<h3>Analytics temporarily unavailable: {e}</h3>", 500


@app.route("/generate-report")
def generate_report():
    try:
        from reports.report_generator import create_pdf_report
        pdf_path = create_pdf_report()
        return send_file(pdf_path, as_attachment=True)
    except Exception as e:
        app.logger.error(f"generate_report error: {e}")
        return f"<h3>Report generation failed: {e}</h3>", 500


@app.route("/routes")
def routes():
    try:
        data        = get_data()
        latest_bins = _build_latest_bins(data)

        priority_bins = [
            {"bin_id": row[0], "fill_level": row[1], "timestamp": row[2]}
            for row in latest_bins.values()
            if row[1] >= 80
        ]
        priority_bins.sort(key=lambda x: x["fill_level"], reverse=True)

        return render_template("routes.html", priority_bins=priority_bins)
    except Exception as e:
        app.logger.error(f"routes error: {e}")
        return f"<h3>Routes temporarily unavailable: {e}</h3>", 500


@app.route("/map")
def map_view():
    try:
        data        = get_data()
        latest_bins = _build_latest_bins(data)

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
    except Exception as e:
        app.logger.error(f"map_view error: {e}")
        return f"<h3>Map temporarily unavailable: {e}</h3>", 500


@app.route("/collections")
def collections():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ce.bin_id,
                   bm.location_name,
                   ce.fill_at_collection,
                   ce.collected_at
            FROM   collection_events ce
            JOIN   bin_master        bm ON ce.bin_id = bm.bin_id
            ORDER  BY ce.collected_at DESC
            LIMIT  100
        """)
        events = cursor.fetchall()
        conn.close()
        return render_template("collections.html", events=events)
    except Exception as e:
        app.logger.error(f"collections error: {e}")
        if conn:
            conn.close()
        return f"<h3>Collections log temporarily unavailable: {e}</h3>", 500


if __name__ == "__main__":
    app.run(debug=True)
