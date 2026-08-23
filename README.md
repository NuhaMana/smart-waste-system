# Smart Waste Monitoring System

A full-stack IoT simulation and Decision Support System (DSS) for smart urban waste collection, built with Python, Flask, SQLite, Leaflet.js, and Chart.js.

---

## Table of Contents

- [Project Overview](#project-overview)
- [System Architecture](#system-architecture)
- [Database Design](#database-design)
- [Routing Algorithm](#routing-algorithm)
- [Decision Support System (DSS)](#decision-support-system-dss)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Setup & Running Instructions](#setup--running-instructions)
- [Key Design Decisions](#key-design-decisions)

---

## Project Overview

This system simulates a network of 5 IoT-enabled smart waste bins deployed across Colombo, Sri Lanka. Every 5 seconds, the simulator writes sensor telemetry (fill level %) to a SQLite database. A Flask web application reads this data in real time to:

1. **Monitor** all bin fill levels on a live dashboard.
2. **Analyse** historical trends and compute a risk index.
3. **Optimise** the collection route using a Nearest-Neighbour heuristic and Haversine distance calculations.
4. **Visualise** the optimised route on an interactive Leaflet.js map.
5. **Generate** a formatted PDF analytics report using ReportLab.

---

## System Architecture

```
┌──────────────────────┐         ┌──────────────────────────┐
│   IoT Simulator      │  every  │       SQLite Database     │
│  simulation/         │──5 sec─▶│   database/db.sqlite3     │
│  simulator.py        │         │                           │
│                      │         │  ┌─────────────────────┐  │
│  • Gradual fill      │         │  │  bin_master (static) │  │
│    (+2 to +8%/cycle) │         │  │  bin_id, lat, lon,  │  │
│  • Auto-collection   │         │  │  location_name,     │  │
│    reset at 95%      │         │  │  capacity_litres    │  │
│  • DB pruning every  │         │  └──────────┬──────────┘  │
│    10 cycles         │         │             │ FK           │
└──────────────────────┘         │  ┌──────────▼──────────┐  │
                                 │  │  telemetry (log)    │  │
                                 │  │  id, bin_id,        │  │
                                 │  │  fill_level,        │  │
                                 │  │  timestamp          │  │
                                 │  └─────────────────────┘  │
                                 └────────────┬─────────────┘
                                              │
                                 ┌────────────▼─────────────┐
                                 │     Flask Backend         │
                                 │       app.py              │
                                 │                           │
                                 │  • haversine()            │
                                 │  • nearest_neighbour_     │
                                 │    route()                │
                                 │  • calculate_route_       │
                                 │    distances()            │
                                 └────────────┬─────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          │                   │                   │
                 ┌────────▼──────┐  ┌─────────▼──────┐  ┌────────▼──────┐
                 │  Dashboard    │  │   Analytics    │  │   Map View   │
                 │  /            │  │   /analytics   │  │   /map        │
                 │               │  │                │  │               │
                 │  Live table,  │  │  Bar chart,    │  │  Leaflet.js,  │
                 │  KPI cards,   │  │  Line chart,   │  │  depot marker,│
                 │  alerts       │  │  DSS panels    │  │  truck anim.  │
                 └───────────────┘  └────────────────┘  └───────────────┘
```

---

## Database Design

The database uses a **two-table relational schema** with a Foreign Key constraint, replacing the original single flat table. This separates static bin metadata from dynamic sensor readings.

### Table 1: `bin_master`

Stores static, immutable metadata for each physical bin. Populated once at startup (seeded automatically).

| Column | Type | Constraint | Description |
|---|---|---|---|
| `bin_id` | `TEXT` | **PRIMARY KEY** | Unique identifier (e.g., `BIN-001`) |
| `location_name` | `TEXT` | `NOT NULL` | Human-readable location name |
| `latitude` | `REAL` | `NOT NULL` | GPS latitude coordinate |
| `longitude` | `REAL` | `NOT NULL` | GPS longitude coordinate |
| `capacity_litres` | `INTEGER` | `NOT NULL` | Physical bin capacity in litres |

### Table 2: `telemetry`

An append-only log of sensor readings. One row is inserted every 5 seconds per bin.

| Column | Type | Constraint | Description |
|---|---|---|---|
| `id` | `INTEGER` | **PRIMARY KEY** `AUTOINCREMENT` | Unique reading ID |
| `bin_id` | `TEXT` | `NOT NULL`, **FOREIGN KEY** → `bin_master.bin_id` | Reference to the physical bin |
| `fill_level` | `INTEGER` | `NOT NULL` | Measured fill level, 0–100% |
| `timestamp` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC time of the reading |

**Referential integrity** is enforced via `PRAGMA foreign_keys = ON` and the `FOREIGN KEY` clause. The database also runs in **WAL (Write-Ahead Logging)** mode to prevent read/write contention between the simulator and the Flask server.

**DB Pruning:** To prevent unbounded table growth, `prune_old_readings(keep_last_n=500)` is called every 10 simulator cycles, retaining only the 500 most recent telemetry rows.

---

## Routing Algorithm

The system implements a classic **Nearest-Neighbour Heuristic** for the Travelling Salesman Problem (TSP), applied to waste collection route optimisation.

### Haversine Formula

All distances are computed using the **Haversine formula**, which calculates the great-circle distance between two geographic coordinates on the surface of the Earth (radius R = 6371 km):

```
a = sin²(Δφ/2) + cos(φ₁) · cos(φ₂) · sin²(Δλ/2)
d = 2R · atan2(√a, √(1−a))
```

Where φ is latitude and λ is longitude, both in radians.

**Implementation:** `haversine(a, b)` in [`app.py`](app.py)

### Nearest-Neighbour Route Construction

**Implementation:** `nearest_neighbour_route(locations)` in [`app.py`](app.py)

**Algorithm steps:**

1. The route begins at a fixed **DEPOT** at coordinates `(6.895°N, 79.840°E)`.
2. All critical bins (fill level ≥ 80%) are placed in an `unvisited` pool.
3. At each step, the algorithm selects the **closest unvisited bin** to the current position using the Haversine distance as the cost function:
   `nearest = min(unvisited, key=lambda p: haversine(current, p))`
4. The selected bin is added to the route, removed from the pool, and becomes the new `current` position.
5. Steps 3–4 repeat until all critical bins have been visited.
6. A **return leg** is added: the truck travels from the last visited bin back to the DEPOT.
7. Total distance is the sum of all Haversine leg distances, rounded to 2 decimal places.

**Time Complexity:** O(n²) where n is the number of critical bins — acceptable for the n ≤ 5 scale of this system.

### Route Efficiency Metric

The efficiency displayed on the Analytics page is computed from **real Haversine distances**, not a formula:

```
traditional_distance = nearest_neighbour_route(ALL 5 bins)   # depot → all → depot
optimized_distance   = nearest_neighbour_route(critical bins) # depot → critical → depot
efficiency (%) = ((traditional - optimized) / traditional) × 100
```

---

## Decision Support System (DSS)

The system implements a **Rule-Based DSS** using threshold logic to classify system risk and generate recommendations. It does not use machine learning or a trained model.

### Classification Rules

| Metric | Rule | Output |
|---|---|---|
| **Fill Level** | `< 50%` | Status: `LOW` (green badge) |
| **Fill Level** | `50% – 79%` | Status: `MEDIUM` (yellow badge) |
| **Fill Level** | `≥ 80%` | Status: `HIGH` (red badge) — bin enters priority collection queue |
| **Risk Score** | `0%` | System State: `OPTIMAL` |
| **Risk Score** | `1–20%` | System State: `LOW RISK` |
| **Risk Score** | `21–50%` | System State: `MEDIUM RISK` |
| **Risk Score** | `> 50%` | System State: `HIGH RISK` |
| **Critical Bins** | `0` | Recommendation: All bins within safe levels |
| **Critical Bins** | `1–2` | Recommendation: Selective collection |
| **Critical Bins** | `≥ 3` | Recommendation: Immediate full dispatch |

**Risk Score formula:**
`risk_score (%) = (critical_bins / total_bins) × 100`

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3, Flask | Web server, routing logic, DSS |
| **Database** | SQLite 3 (raw `sqlite3` module) | Relational telemetry storage |
| **IoT Simulation** | Python (`random`, `time`) | Gradual fill simulation |
| **Mapping** | Leaflet.js + OpenStreetMap | Interactive route visualisation |
| **Charts** | Chart.js | Bar chart (fill levels), Line chart (trend) |
| **PDF Reports** | ReportLab + Matplotlib | Analytics report generation |
| **Frontend** | HTML5, Bootstrap 5, Vanilla CSS | Responsive UI |
| **Geo-computation** | Haversine formula (pure Python math) | Great-circle distance calculation |

---

## Project Structure

```
smart-waste-system/
│
├── app.py                          # Flask application — routes, haversine, NN algorithm
│
├── database/
│   ├── db.py                       # Schema creation, seeding, insert, prune, get_bin_locations
│   └── db.sqlite3                  # SQLite database file (auto-created on first run)
│
├── simulation/
│   └── simulator.py                # IoT simulator — gradual fill, collection events, DB pruning
│
├── templates/
│   ├── base.html                   # Shared layout (navbar, Bootstrap)
│   ├── index.html                  # Landing page
│   ├── dashboard.html              # Live monitoring table + KPI cards + alerts
│   ├── analytics.html              # Charts + DSS panels + route efficiency
│   ├── routes.html                 # Priority collection queue table
│   └── map.html                    # Leaflet.js map + animated truck + depot marker
│
├── reports/
│   ├── report_generator.py         # ReportLab PDF builder + Matplotlib chart generator
│   └── Smart_Waste_Analytics_Report.pdf   # Generated on demand via /generate-report
│
├── static/
│   ├── css/style.css
│   └── js/ui.js
│
├── requirements.txt
└── README.md                       # This file
```

---

## Setup & Running Instructions

### Prerequisites

- Python 3.8 or higher
- pip

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the IoT simulator (in one terminal)

```bash
python simulation/simulator.py
```

The simulator will automatically create the database schema, seed the 5 bins into `bin_master`, and begin writing telemetry readings every 5 seconds. The console will show fill levels incrementing gradually, and collection events when a bin exceeds 95%.

### 3. Start the Flask server (in a second terminal)

```bash
python app.py
```

Open your browser at: **http://127.0.0.1:5000**

### 4. Navigate the application

| URL | Page |
|---|---|
| `http://127.0.0.1:5000/` | Live monitoring dashboard |
| `http://127.0.0.1:5000/analytics` | Analytics + DSS + route efficiency |
| `http://127.0.0.1:5000/routes` | Priority collection queue |
| `http://127.0.0.1:5000/map` | Interactive optimised route map |
| `http://127.0.0.1:5000/generate-report` | Download PDF analytics report |

---

## Key Design Decisions

### Why SQLite over a full RDBMS?
SQLite is appropriate for a single-node IoT simulation system. Its file-based nature eliminates server setup overhead, and WAL mode provides sufficient concurrent read/write performance for the 5-second telemetry cycle.

### Why Nearest-Neighbour over an exact TSP solver?
Exact TSP solvers (e.g., branch-and-bound) are NP-hard in the general case. For n ≤ 5 bins, the Nearest-Neighbour heuristic consistently produces near-optimal routes in O(n²) time, making it well-suited for real-time web response.

### Why a Rule-Based DSS rather than Machine Learning?
The system's decision boundaries (fill level thresholds, risk classification) are well-defined domain rules from waste management practice. A rule-based approach is transparent, explainable, and requires no training data — appropriate for a real-time monitoring application where interpretability is critical.

### Why Haversine over Euclidean distance?
Waste bin coordinates span multiple kilometres. Euclidean distance on latitude/longitude coordinates introduces significant error due to the curvature of the Earth. Haversine computes the correct great-circle distance, producing accurate km values for route planning.
