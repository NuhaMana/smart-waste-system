import matplotlib
matplotlib.use("Agg")

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak,
    Frame,
    PageTemplate,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas


DB_PATH = "database/db.sqlite3"


def generate_report_data():
    """
    Queries the database and computes all statistics needed for the PDF.
    Raises ValueError if no telemetry data exists (simulator not yet run).
    Raises sqlite3.Error if the database is inaccessible.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)

        # --- Telemetry data ---
        df = pd.read_sql_query(
            """
            SELECT bin_id, fill_level, timestamp
            FROM   telemetry
            ORDER  BY timestamp
            """,
            conn
        )

        if df.empty:
            raise ValueError(
                "No telemetry data found. "
                "Start the simulator first, then generate the report."
            )

        # --- Collection events ---
        events_df = pd.read_sql_query(
            """
            SELECT ce.bin_id,
                   bm.location_name,
                   ce.fill_at_collection,
                   ce.collected_at
            FROM   collection_events ce
            JOIN   bin_master        bm ON ce.bin_id = bm.bin_id
            ORDER  BY ce.collected_at DESC
            """,
            conn
        )

    except sqlite3.Error as e:
        raise RuntimeError(f"Database error in generate_report_data: {e}") from e
    finally:
        if conn:
            conn.close()

    # -------------------------------------------------------------------------
    # TELEMETRY ANALYTICS
    # -------------------------------------------------------------------------
    total_records    = len(df)
    average_fill     = round(df["fill_level"].mean(), 1)
    critical_records = len(df[df["fill_level"] >= 80])
    highest_fill     = int(df["fill_level"].max())
    highest_bin      = df.loc[df["fill_level"].idxmax(), "bin_id"]
    low_risk         = len(df[df["fill_level"] < 50])
    medium_risk      = len(df[(df["fill_level"] >= 50) & (df["fill_level"] < 80)])
    high_risk        = len(df[df["fill_level"] >= 80])

    # -------------------------------------------------------------------------
    # COLLECTION EVENTS ANALYTICS
    # -------------------------------------------------------------------------
    total_collections = len(events_df)
    if total_collections > 0:
        most_collected        = events_df["bin_id"].value_counts().idxmax()
        avg_fill_at_collection = round(events_df["fill_at_collection"].mean(), 1)
        recent_events         = events_df.head(10).values.tolist()
    else:
        most_collected         = "N/A"
        avg_fill_at_collection = 0
        recent_events          = []

    # -------------------------------------------------------------------------
    # HISTORICAL TREND CHART
    # -------------------------------------------------------------------------
    trend_path = "reports/historical_trend.png"
    try:
        bin_colours = {
            "BIN-001": "#1a73e8",
            "BIN-002": "#28a745",
            "BIN-003": "#ffc107",
            "BIN-004": "#dc3545",
            "BIN-005": "#9b59b6",
        }
        fig, ax = plt.subplots(figsize=(9, 4))
        
        # Prepare timestamp as datetime for clean, formatted date scaling
        df_chart = df.copy()
        df_chart["dt"] = pd.to_datetime(df_chart["timestamp"], errors="coerce")
        
        for bin_id, group in df_chart.groupby("bin_id"):
            sample_group = group.tail(60)
            ax.plot(
                sample_group["dt"],
                sample_group["fill_level"],
                label=bin_id,
                linewidth=2,
                color=bin_colours.get(bin_id, "#333333")
            )
        ax.axhline(y=80, color="red", linestyle="--", linewidth=1, label="Critical threshold (80%)")
        ax.set_title("Historical Waste Fill Level Trend — Per Bin")
        ax.set_xlabel("Time (HH:MM)")
        ax.set_ylabel("Fill Level (%)")
        ax.set_ylim(0, 105)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
        fig.autofmt_xdate(rotation=30)
        
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(trend_path, dpi=150)
    finally:
        plt.close()

    # -------------------------------------------------------------------------
    # RISK DISTRIBUTION CHART
    # -------------------------------------------------------------------------
    risk_path = "reports/risk_distribution.png"
    try:
        plt.figure(figsize=(6, 4))
        plt.bar(
            ["Low (<50%)", "Medium (50-79%)", "High (≥80%)"],
            [low_risk, medium_risk, high_risk],
            color=["#28a745", "#ffc107", "#dc3545"]
        )
        plt.title("Waste Bin Risk Distribution")
        plt.xlabel("Risk Level")
        plt.ylabel("Number of Records")
        plt.tight_layout()
        plt.savefig(risk_path, dpi=150)
    finally:
        plt.close()

    return {
        "generated_time":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_records":         total_records,
        "average_fill":          average_fill,
        "critical_records":      critical_records,
        "highest_bin":           highest_bin,
        "highest_fill":          highest_fill,
        "trend_path":            trend_path,
        "risk_path":             risk_path,
        # Collection events
        "total_collections":     total_collections,
        "most_collected":        most_collected,
        "avg_fill_at_collection": avg_fill_at_collection,
        "recent_events":         recent_events,
    }


def add_page_decorations(canvas, doc):
    width, height = letter
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#1d2b45"))
    canvas.setLineWidth(1)
    canvas.rect(20, 20, width - 40, height - 40)
    canvas.setFillColor(colors.HexColor("#1d2b45"))
    canvas.rect(20, height - 60, width - 40, 40, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(40, height - 45, "SMART WASTE ANALYTICS REPORT")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.grey)
    canvas.drawString(40, 25, "Generated by Smart Waste Monitoring System")
    canvas.drawRightString(width - 40, 25, f"Page {doc.page}")
    canvas.restoreState()


def create_pdf_report():
    """
    Builds the full PDF report. Propagates exceptions with descriptive messages
    so the Flask route can render a friendly error instead of crashing.
    """
    data = generate_report_data()   # raises ValueError / RuntimeError on failure

    pdf_path = "reports/Smart_Waste_Analytics_Report.pdf"

    document = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=40, leftMargin=40,
        topMargin=80,   bottomMargin=60
    )
    frame = Frame(40, 60, letter[0] - 80, letter[1] - 120, id="normal")
    document.addPageTemplates([
        PageTemplate(
            id="ReportTemplate",
            frames=[frame],
            onPage=add_page_decorations
        )
    ])

    styles  = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        name="SectionHeading",
        fontSize=14,
        textColor=colors.HexColor("#1d2b45"),
        spaceAfter=10
    )
    content = []

    # ------------------------------------------------------------------ TITLE
    content.append(Paragraph(
        "<font size=24><b>Smart Waste Monitoring System</b></font>",
        styles["Title"]
    ))
    content.append(Spacer(1, 8))
    content.append(Paragraph(
        "<font size=16>Analytics &amp; Performance Report</font>",
        styles["Heading2"]
    ))
    content.append(Spacer(1, 20))
    content.append(Paragraph(
        f"<b>Report Generated:</b> {data['generated_time']}",
        styles["Normal"]
    ))
    content.append(Paragraph(
        "<b>Generated By:</b> Smart Waste Monitoring System",
        styles["Normal"]
    ))
    content.append(Spacer(1, 20))

    # -------------------------------------------------- SYSTEM OVERVIEW
    content.append(Paragraph("<b>System Overview</b>", heading_style))
    content.append(Paragraph(
        "This report presents analytics generated from the smart waste monitoring "
        "system. The system analyses bin fill levels, identifies collection "
        "priorities using a rule-based DSS, and logs collection events separately "
        "from sensor telemetry.",
        styles["Normal"]
    ))
    content.append(Spacer(1, 20))

    # -------------------------------------------------- SUMMARY TABLE
    summary_data = [
        ["Metric", "Value"],
        ["Total Telemetry Records", data["total_records"]],
        ["Average Fill Level",      f"{data['average_fill']}%"],
        ["Critical Records (≥80%)", data["critical_records"]],
        ["Highest Risk Bin",        data["highest_bin"]],
        ["Highest Fill Level",      f"{data['highest_fill']}%"],
        ["Total Collection Events", data["total_collections"]],
        ["Most Collected Bin",      data["most_collected"]],
        ["Avg Fill at Collection",  f"{data['avg_fill_at_collection']}%"],
    ]
    tbl = Table(summary_data, colWidths=[300, 160])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#1d2b45")),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND",   (0, 1), (-1, -1), colors.whitesmoke),
        ("BOTTOMPADDING",(0, 0), (-1, 0),  10),
        ("TOPPADDING",   (0, 0), (-1, 0),  10),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
    ]))
    content.append(tbl)
    content.append(Spacer(1, 25))
    content.append(PageBreak())

    # -------------------------------------------------- TREND CHART
    content.append(Paragraph("Historical Trend Analysis", styles["Heading2"]))
    content.append(Image(data["trend_path"], width=470, height=230))
    content.append(Paragraph(
        "Figure 1. Historical waste fill level trend across recorded sensor readings.",
        styles["Normal"]
    ))
    content.append(Spacer(1, 30))

    # -------------------------------------------------- RISK CHART
    content.append(Paragraph("Risk Distribution Analysis", styles["Heading2"]))
    content.append(Image(data["risk_path"], width=420, height=260))
    content.append(Paragraph(
        "Figure 2. Distribution of low, medium, and high-risk waste records.",
        styles["Normal"]
    ))
    content.append(Spacer(1, 20))
    content.append(PageBreak())

    # -------------------------------------------------- COLLECTION EVENTS
    content.append(Paragraph("Collection Events Summary", styles["Heading2"]))
    content.append(Paragraph(
        "The following table summarises bin collection events recorded in the "
        "<i>collection_events</i> table — stored separately from sensor telemetry "
        "to enable clean queryability of actual emptying events.",
        styles["Normal"]
    ))
    content.append(Spacer(1, 12))

    if data["recent_events"]:
        event_rows = [["Bin ID", "Location", "Fill at Collection (%)", "Collected At"]]
        for ev in data["recent_events"]:
            event_rows.append([ev[0], ev[1], f"{ev[2]}%", str(ev[3])])
        ev_tbl = Table(event_rows, colWidths=[70, 140, 120, 140])
        ev_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#1d2b45")),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND",   (0, 1), (-1, -1), colors.whitesmoke),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ]))
        content.append(ev_tbl)
    else:
        content.append(Paragraph(
            "No collection events have been recorded yet. "
            "Events appear here once bins reach the 95% threshold during simulation.",
            styles["Normal"]
        ))

    content.append(Spacer(1, 20))

    # -------------------------------------------------- SYSTEM ASSESSMENT
    content.append(Table(
        [[Paragraph(
            "<b>System Assessment</b><br/><br/>"
            "The analytics module successfully evaluates historical waste "
            "accumulation trends and identifies high-priority collection "
            "requirements. The rule-based DSS applies configurable fill-level "
            "thresholds to generate actionable recommendations. Collection events "
            "are stored in a dedicated table, enabling independent analysis of "
            "collection frequency and bin-level performance.",
            styles["Normal"]
        )]],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
            ("BOX",        (0, 0), (-1, -1), 1, colors.HexColor("#1d2b45")),
            ("PADDING",    (0, 0), (-1, -1), 12),
        ])
    ))

    document.build(content)
    return pdf_path


if __name__ == "__main__":
    pdf = create_pdf_report()
    print("Generated:", pdf)