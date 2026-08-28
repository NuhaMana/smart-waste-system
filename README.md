# Smart Waste Monitoring System

An intelligent, full-stack IoT simulation and Rule-Based Decision Support System (DSS) for smart urban waste collection, built with Python, Flask, SQLite (WAL mode), Leaflet.js, and Chart.js.

---

## Table of Contents

- [Project Overview](#project-overview)
- [System Architecture](#system-architecture)
- [Database Design](#database-design)
- [Physical Waste Volume Calculation](#physical-waste-volume-calculation)
- [Routing Algorithm & Baseline Comparison](#routing-algorithm--baseline-comparison)
- [Decision Support System (DSS)](#decision-support-system-dss)
- [Automated Testing Suite (40 Tests)](#automated-testing-suite-40-tests)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Setup & Running Instructions](#setup--running-instructions)
- [Submission & Packaging Guidelines](#submission--packaging-guidelines)
- [Key Design Decisions](#key-design-decisions)

---

## Project Overview

This system simulates a network of 5 IoT-enabled smart waste bins deployed across municipal zones in Colombo, Sri Lanka. Every 5 seconds, an IoT simulation engine writes sensor telemetry (fill level %) to a normalized SQLite database. A Flask web application processes this data in real time to:

1. **Monitor** all bin fill levels and calculated waste volume in litres via an asynchronous AJAX dashboard.
2. **Analyse** historical trends, risk indices, and operational workload.
3. **Optimise** collection routing dynamically using the Haversine great-circle formula and Nearest-Neighbour Traveling Salesperson Problem (TSP) heuristic.
4. **Visualise** depot-anchored collection routes and animated vehicle dispatch on an interactive Leaflet.js map.
5. **Track Collections** in a dedicated relational table decoupled from continuous sensor telemetry.
6. **Generate** structured PDF analytics reports with ReportLab and Matplotlib visualisations.
7. **Verify** system reliability through a comprehensive 40-test automated verification suite.

---

## System Architecture

```
┌─────────────────────────┐         ┌────────────────────────────────────────────────────────┐
│     IoT Simulator       │  every  │                  SQLite Database                       │
│  simulation/            │──5 sec─▶│               database/db.sqlite3                      │
│  simulator.py           │         │                                                        │
│                         │         │  ┌──────────────────────────────────────────────────┐  │
│  • Location fill rates  │         │  │              bin_master (static)                 │  │
│    (4–9%/cycle + noise) │         │  │  bin_id, location_name, lat, lon,               │  │
│  • Collection trigger   │         │  │  capacity_litres, fill_rate                     │  │
│    at ≥ 95% threshold   │         │  └───────────────┬──────────────────┬───────────────┘  │
│  • Telemetry pruned     │         │                  │ FK               │ FK           │
│    (keeps 5000 rows)    │         │  ┌───────────────▼────────┐  ┌──────▼────────────┐  │
└─────────────────────────┘         │  │    telemetry (log)     │  │ collection_events │  │
                                    │  │  id, bin_id,           │  │ id, bin_id,       │  │
                                    │  │  fill_level, timestamp │  │ fill_at_coll, time│  │
                                    │  └────────────────────────┘  └───────────────────┘  │
                                    └──────────────────────────┬─────────────────────────────┘
                                                               │
                                    ┌──────────────────────────▼─────────────────────────────┐
                                    │                     Flask Backend                      │
                                    │                       app.py                           │
                                    │                                                        │
                                    │  • haversine()                • /api/dashboard (AJAX)  │
                                    │  • nearest_neighbour_route()  • Volume in Litres calc  │
                                    │  • sequential_route_distance()• Exception handling     │
                                    └──────────────────────────┬─────────────────────────────┘
                                                               │
        ┌─────────────────────────┼────────────────────────────┼──────────────────────────┐
        │                         │                            │                          │
┌───────▼────────┐      ┌─────────▼────────┐         ┌─────────▼────────┐       ┌─────────▼────────┐
│  Dashboard     │      │   Analytics      │         │   Routes & Map   │       │ Collections Log  │
│  /             │      │   /analytics     │         │   /routes, /map  │       │ /collections     │
│                │      │                  │         │                  │       │                  │
│ AJAX polling,  │      │ Bar/Line charts, │         │ Priority table,  │       │ Relational JOIN  │
│ Volume (L),    │      │ DSS suggestions, │         │ Leaflet.js map,  │       │ of past emptying │
│ Live alerts    │      │ efficiency gain  │         │ truck animation  │       │ audit events     │
└────────────────┘      └──────────────────┘         └──────────────────┘       └──────────────────┘
```

---

## Database Design

The database uses a **three-table normalized relational schema** with enforced Foreign Key constraints and **WAL (Write-Ahead Logging)** mode. This design cleanly decouples static bin metadata, high-frequency continuous telemetry, and discrete bin-emptying events.

### Table 1: `bin_master` (Static Metadata)

Stores immutable metadata and simulation parameters for each physical bin. Seeded automatically at application startup.

| Column | Type | Constraint | Description |
|---|---|---|---|
| `bin_id` | `TEXT` | **PRIMARY KEY** | Unique identifier (e.g., `BIN-001`) |
| `location_name` | `TEXT` | `NOT NULL` | Human-readable location description |
| `latitude` | `REAL` | `NOT NULL` | GPS latitude coordinate |
| `longitude` | `REAL` | `NOT NULL` | GPS longitude coordinate |
| `capacity_litres` | `INTEGER` | `NOT NULL` | Physical container capacity (120 Litres) |
| `fill_rate` | `INTEGER` | `NOT NULL` | Calibrated accumulation rate (4–9% / cycle) |

### Table 2: `telemetry` (Continuous Time-Series Log)

An append-only log of sensor readings written every 5 seconds per bin.

| Column | Type | Constraint | Description |
|---|---|---|---|
| `id` | `INTEGER` | **PRIMARY KEY** `AUTOINCREMENT` | Unique reading identifier |
| `bin_id` | `TEXT` | `NOT NULL`, **FOREIGN KEY** → `bin_master.bin_id` | Reference to the monitored bin |
| `fill_level` | `INTEGER` | `NOT NULL` | Measured fill level percentage (0–100%) |
| `timestamp` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of the measurement |

### Table 3: `collection_events` (Discrete Emptying Log)

Records discrete emptying events when a bin reaches the collection threshold ($\ge 95\%$).

| Column | Type | Constraint | Description |
|---|---|---|---|
| `id` | `INTEGER` | **PRIMARY KEY** `AUTOINCREMENT` | Unique event identifier |
| `bin_id` | `TEXT` | `NOT NULL`, **FOREIGN KEY** → `bin_master.bin_id` | Reference to the collected bin |
| `fill_at_collection` | `INTEGER` | `NOT NULL` | Fill percentage at the moment of collection |
| `collected_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | Timestamp when bin was emptied |

**Concurrency & Maintenance:**
- Referential integrity is enforced with `PRAGMA foreign_keys = ON`.
- High-concurrency read-write capability is enabled via `PRAGMA journal_mode = WAL`.
- Table maintenance is managed by `prune_old_readings(keep_last_n=5000)`, keeping ~14 hours of time-series history.

---

## Physical Waste Volume Calculation

To provide true physical operational realism beyond raw percentages, the system calculates the actual volume of accumulated waste in litres:

$$\text{Volume (Litres)} = \frac{\text{Fill Level (\%)}}{100} \times \text{Capacity (Litres)}$$

- Displayed across the **Dashboard live table**, **JSON API payload**, and **Analytics Network Volume Card**.
- Network-wide metrics calculate total accumulated volume against total capacity ($600\text{ L}$ across 5 bins).

---

## Routing Algorithm & Baseline Comparison

### 1. Haversine Great-Circle Distance
All geospatial calculations use the spherical Earth Haversine formula ($R = 6371\text{ km}$):

$$a = \sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)$$

$$d = 2R \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1-a}\right)$$

### 2. Nearest-Neighbour Heuristic (TSP)
- **Origin & Destination:** Fixed Central Depot `(6.895°N, 79.840°E)`.
- **Target Selection:** Evaluates only critical bins ($\ge 80\%$).
- **Route Construction:** Greedily selects the nearest unvisited coordinate at each step, returning to the depot upon completion.

### 3. Objective Baseline Benchmarking
Efficiency is benchmarked against an authentic, deterministic sequential baseline route ($\text{DEPOT} \rightarrow \text{BIN-001} \dots \text{BIN-005} \rightarrow \text{DEPOT} = 12.36\text{ km}$):

$$\text{Efficiency Gain (\%)} = \begin{cases} 
\text{round}\left(\frac{\text{Traditional Distance} - \text{Optimized Distance}}{\text{Traditional Distance}} \times 100\right) & \text{if critical bins} > 0 \\
0\% & \text{if critical bins} = 0
\end{cases}$$

---

## Decision Support System (DSS)

The system implements a transparent, rule-based DSS that classifies risk and prescribes actionable dispatch instructions:

| Metric | Condition | Classification / Output |
|---|---|---|
| **Bin Fill Level** | $< 50\%$ | `LOW` (Green) |
| **Bin Fill Level** | $50\% - 79\%$ | `MEDIUM` (Yellow) |
| **Bin Fill Level** | $\ge 80\%$ | `HIGH` (Red) — Priority Dispatch Queue |
| **Network Risk Score** | $0\%$ | `OPTIMAL` |
| **Network Risk Score** | $1\% - 20\%$ | `LOW RISK` |
| **Network Risk Score** | $21\% - 50\%$ | `MEDIUM RISK` |
| **Network Risk Score** | $> 50\%$ | `HIGH RISK` |
| **Critical Bins** | $0$ | "All bins are currently operating within safe levels." |
| **Critical Bins** | $1 - 2$ | "Selective smart collection is recommended for critical bins." |
| **Critical Bins** | $\ge 3$ | "Multiple critical bins detected. Immediate optimised collection required." |

$$\text{Risk Score (\%)} = \left(\frac{\text{Critical Bins}}{\text{Total Bins}}\right) \times 100$$

---

## Automated Testing Suite (40 Tests)

The codebase includes an extensive automated test suite covering 4 distinct testing levels:

```bash
# Run all 40 automated tests:
python -m unittest discover -s tests -p "test_*.py" -v
```

| Test Suite | File | Count | Scope |
|---|---|---|---|
| **Unit Tests** | `tests/test_core.py` | 24 | Haversine formula, volume math, Nearest-Neighbour TSP, sequential baseline, DB CRUD. |
| **Concurrency Tests** | `tests/test_concurrency.py` | 3 | Multi-threaded SQLite WAL simultaneous reads, concurrent writes, and collection logging. |
| **Integration Tests** | `tests/test_integration.py` | 8 | End-to-end Flask test client covering all HTTP routes, JSON API, template rendering, and error traps. |
| **Report Engine Tests** | `tests/test_report.py` | 5 | Statistical data aggregation, empty-state exception handling, and PDF binary `%PDF-` validation. |
| **Total** | | **40** | **100% Passing with Zero Failures** |

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend Framework** | Python 3, Flask | HTTP server, REST endpoints, routing logic, DSS engine |
| **Database** | SQLite 3 (WAL Mode, Foreign Keys) | Normalized relational storage with high concurrency |
| **IoT Simulation** | Python (`random`, `time`) | Location-calibrated telemetry accumulation |
| **Geospatial Processing** | Haversine Formula (Pure Math) | Great-circle distance calculations & TSP heuristic |
| **Interactive Maps** | Leaflet.js, OpenStreetMap | Dynamic waypoint mapping and vehicle animation |
| **Data Visualisation** | Chart.js, Matplotlib | Real-time browser charts and PDF graph generation |
| **PDF Reporting** | ReportLab | Automated executive PDF analytics generation |
| **Frontend Styling** | Bootstrap 5, Vanilla CSS | Dark theme UI with responsive components |
| **Testing** | Python `unittest`, `threading` | Automated unit, concurrency, integration, and report testing |

---

## Project Structure

```
smart-waste-system/
│
├── app.py                          # Flask application — routes, haversine, NN TSP, DSS logic
│
├── database/
│   ├── db.py                       # Schema definition, migrations, seeding, helpers
│   └── db.sqlite3                  # SQLite database file (auto-generated on first run)
│
├── simulation/
│   └── simulator.py                # IoT telemetry generator, collection events, DB pruner
│
├── templates/
│   ├── base.html                   # Master layout with navigation bar and live badge
│   ├── dashboard.html              # Real-time AJAX dashboard with Volume (L) and KPI cards
│   ├── analytics.html              # Chart.js analytics, Rule-Based DSS status, comparison
│   ├── routes.html                 # Priority collection queue table (sorted by urgency)
│   ├── map.html                    # Leaflet.js interactive map with animated truck route
│   └── collections.html            # Collection event audit log with relational JOINs
│
├── reports/
│   ├── report_generator.py         # ReportLab PDF synthesizer & Matplotlib trend chart builder
│   └── Smart_Waste_Analytics_Report.pdf  # Generated report artifact
│
├── static/
│   ├── css/style.css               # Global dark UI styling
│   └── js/ui.js                    # UI interactions, active navigation highlighting
│
├── tests/
│   ├── __init__.py                 # Test package initialization
│   ├── test_core.py                # Unit test suite (24 tests)
│   ├── test_concurrency.py         # Multi-threaded SQLite concurrency tests (3 tests)
│   ├── test_integration.py         # End-to-end Flask route integration tests (8 tests)
│   └── test_report.py              # PDF engine statistical and binary integrity tests (5 tests)
│
├── requirements.txt                # Pinned production dependencies
└── README.md                       # Complete technical documentation
```

---

## Setup & Running Instructions

### Prerequisites
- Python 3.8 to 3.13
- pip package manager

### 1. Set Up Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate on Windows:
.\venv\Scripts\activate

# Activate on macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the IoT Simulator (Terminal 1)

```bash
python simulation/simulator.py
```
*The simulator creates the database schema, seeds the 5 bins, and starts generating real-time telemetry every 5 seconds.*

### 4. Start the Flask Server (Terminal 2)

```bash
python app.py
```
*Open your browser and navigate to: **`http://127.0.0.1:5000`***

### 5. Application URL Routes

| URL Route | Page Name | Primary Function |
|---|---|---|
| `http://127.0.0.1:5000/` | Live Dashboard | Real-time monitoring, Volume (L), AJAX updates |
| `http://127.0.0.1:5000/analytics` | Analytics & DSS | Fill analysis, DSS recommendation, efficiency metric |
| `http://127.0.0.1:5000/routes` | Route Priorities | Urgency-sorted list of bins requiring collection |
| `http://127.0.0.1:5000/map` | Geospatial Map | Leaflet.js depot-anchored route & truck animation |
| `http://127.0.0.1:5000/collections` | Collection Log | Relational history of emptied bins and timestamps |
| `http://127.0.0.1:5000/generate-report` | PDF Generator | Download formatted PDF analytics report |
| `http://127.0.0.1:5000/api/dashboard` | REST API | JSON endpoint queried every 10s by frontend |

---

## Submission & Packaging Guidelines

When packaging this project for academic submission (ZIP archive), follow these industry best practices:

### What to EXCLUDE from the ZIP file:
- `venv/` (Virtual environment contains thousands of machine-specific binary files; examiners will recreate this from `requirements.txt`).
- `__pycache__/` and `.pytest_cache/` (Compiled Python bytecode).
- Temporary debug files.

### What to INCLUDE in the ZIP file:
- `app.py`
- `requirements.txt`
- `README.md`
- `database/` (`db.py`)
- `simulation/` (`simulator.py`)
- `templates/` (All 6 HTML templates)
- `static/` (`style.css`, `ui.js`)
- `reports/` (`report_generator.py`)
- `tests/` (All test suites)

### Creating the ZIP File via PowerShell:
```powershell
Compress-Archive -Path app.py, requirements.txt, README.md, database, simulation, templates, static, reports, tests -DestinationPath smart-waste-system-submission.zip
```

---

## Key Design Decisions

### Why SQLite WAL Mode over Heavyweight RDBMS?
For an academic edge prototype, SQLite eliminates complex client-server installation overhead. Enabling Write-Ahead Logging (`PRAGMA journal_mode=WAL`) allows concurrent read access from Flask while the simulator performs periodic writes without database lock contention.

### Why Haversine over Euclidean Distance?
Geographic coordinates on the Earth's surface follow spherical geometry. Planar Euclidean calculations on latitude/longitude introduce severe projection distortions. The Haversine formula produces mathematically accurate great-circle kilometre distances.

### Why Transparent Rule-Based DSS over Machine Learning?
Municipal waste collection thresholds (e.g., $80\%$ critical trigger) are explicit operational constraints. A rule-based DSS provides deterministic, explainable, and zero-latency decision outputs without requiring arbitrary synthetic dataset training.
