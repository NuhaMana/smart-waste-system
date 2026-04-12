import random
import time
from database.db import create_table, insert_bin_data

bins = ["BIN-001", "BIN-002", "BIN-003", "BIN-004", "BIN-005"]


def generate_data():
    data = []

    for bin_id in bins:
        fill_level = random.randint(0, 100)

        data.append({
            "bin_id": bin_id,
            "fill_level": fill_level
        })

    return data


if __name__ == "__main__":
    create_table()  # ensure table exists

    print("Simulation started... (CTRL + C to stop)")

    try:
        while True:
            simulated_data = generate_data()

            for item in simulated_data:
                print(item)

                # 🔥 SAVE TO DATABASE
                insert_bin_data(item["bin_id"], item["fill_level"])

            print("-" * 40)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nSimulation stopped safely.")