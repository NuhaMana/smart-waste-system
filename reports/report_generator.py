import matplotlib

matplotlib.use("Agg")

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter


DB_PATH = "database/db.sqlite3"


def generate_report_data():

    conn = sqlite3.connect(DB_PATH)


    df = pd.read_sql_query(
        """
        SELECT bin_id, fill_level, timestamp
        FROM bins
        ORDER BY timestamp
        """,
        conn
    )


    conn.close()


    # -------------------------
    # ANALYTICS
    # -------------------------


    total_records = len(df)


    average_fill = round(
        df["fill_level"].mean(),
        1
    )


    critical_records = len(
        df[df["fill_level"] >= 80]
    )


    highest_fill = df["fill_level"].max()


    highest_bin = df.loc[
        df["fill_level"].idxmax(),
        "bin_id"
    ]


    low_risk = len(
        df[df["fill_level"] < 50]
    )


    medium_risk = len(
        df[
            (df["fill_level"] >= 50)
            &
            (df["fill_level"] < 80)
        ]
    )


    high_risk = len(
        df[df["fill_level"] >= 80]
    )



    # -------------------------
    # HISTORICAL GRAPH
    # -------------------------


    trend_path = "reports/historical_trend.png"


    plt.figure(figsize=(9,4))


    plt.plot(
        df["timestamp"],
        df["fill_level"],
        linewidth=3
    )


    plt.title(
        "Historical Waste Fill Level Trend"
    )


    plt.xlabel("Time")

    plt.ylabel(
        "Fill Level (%)"
    )


    plt.xticks(rotation=45)

    plt.grid(alpha=0.3)

    plt.tight_layout()


    plt.savefig(
        trend_path,
        dpi=300
    )


    plt.close()



    # -------------------------
    # RISK CHART
    # -------------------------


    risk_path = "reports/risk_distribution.png"


    plt.figure(figsize=(6,4))


    plt.bar(

        ["Low","Medium","High"],

        [
            low_risk,
            medium_risk,
            high_risk
        ]

    )


    plt.title(
        "Waste Bin Risk Distribution"
    )


    plt.xlabel(
        "Risk Level"
    )


    plt.ylabel(
        "Number of Records"
    )


    plt.tight_layout()


    plt.savefig(
        risk_path,
        dpi=300
    )


    plt.close()



    return {


        "generated_time":
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),


        "total_records":
        total_records,


        "average_fill":
        average_fill,


        "critical_records":
        critical_records,


        "highest_bin":
        highest_bin,


        "highest_fill":
        highest_fill,


        "trend_path":
        trend_path,


        "risk_path":
        risk_path

    }




def create_pdf_report():


    data = generate_report_data()


    pdf_path = (
        "reports/"
        "Smart_Waste_Analytics_Report.pdf"
    )


    document = SimpleDocTemplate(
        pdf_path,
        pagesize=letter
    )


    styles = getSampleStyleSheet()


    content = []



    # TITLE


    content.append(

        Paragraph(
            """
            Smart Waste Monitoring System<br/>
            Analytics & Performance Report
            """,

            styles["Title"]

        )

    )


    content.append(
        Spacer(1,20)
    )



    content.append(

        Paragraph(

            f"""
            Report Generated:
            {data['generated_time']}
            """,

            styles["Normal"]

        )

    )



    content.append(
        Spacer(1,20)
    )



    # SYSTEM OVERVIEW


    content.append(

        Paragraph(

            """
            System Overview
            """,

            styles["Heading2"]

        )

    )


    content.append(

        Paragraph(

            """
            This report presents analytics generated
            from the smart waste monitoring system.
            The system analyses bin fill levels and
            identifies collection priorities.
            """,

            styles["Normal"]

        )

    )


    content.append(
        Spacer(1,20)
    )



    # SUMMARY TABLE


    table_data = [


        [
            "Metric",
            "Value"
        ],


        [
            "Total Records Analysed",
            data["total_records"]
        ],


        [
            "Average Fill Level",
            f"{data['average_fill']}%"
        ],


        [
            "Critical Records",
            data["critical_records"]
        ],


        [
            "Highest Risk Bin",
            data["highest_bin"]
        ],


        [
            "Highest Fill Level",
            f"{data['highest_fill']}%"
        ]


    ]



    table = Table(table_data)


    table.setStyle(

        TableStyle(

            [

            ("GRID",
             (0,0),
             (-1,-1),
             0.5,
             None),


            ("BACKGROUND",
             (0,0),
             (-1,0),
             "#cccccc")

            ]

        )

    )


    content.append(table)



    content.append(
        Spacer(1,25)
    )



    # TREND GRAPH


    content.append(

        Paragraph(
            "Historical Trend Analysis",
            styles["Heading2"]
        )

    )


    content.append(

        Image(
            data["trend_path"],
            width=400,
            height=180
        )

    )


    content.append(
        Spacer(1,20)
    )



    # RISK GRAPH


    content.append(

        Paragraph(
            "Risk Distribution Analysis",
            styles["Heading2"]
        )

    )


    content.append(

        Image(
            data["risk_path"],
            width=300,
            height=200
        )

    )


    content.append(
        Spacer(1,20)
    )



    # CONCLUSION


    content.append(

        Paragraph(

            """
            System Assessment:<br/>

            The analytics module successfully evaluates
            historical waste accumulation patterns.
            The generated insights support efficient
            monitoring and collection planning.

            """,

            styles["Normal"]

        )

    )



    document.build(content)



    return pdf_path





if __name__ == "__main__":

    pdf = create_pdf_report()

    print(
        "Generated:",
        pdf
    )
    