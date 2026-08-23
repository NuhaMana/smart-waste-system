import random
import time
from database.db import create_tables, insert_reading, prune_old_readings

BINS = ["BIN-001", "BIN-002", "BIN-003", "BIN-004", "BIN-005"]

# Each bin starts at a realistic staggered fill level (not all zero at once)
fill_state = {bin_id: random.randint(10, 40) for bin_id in BINS}


def simulate_cycle():
    """
    Increments each bin's fill level by a realistic random amount per cycle.
    If a bin reaches the collection threshold (>= 95%), a collection event
    is triggered: a 0% reading is written to the database to mark the reset,
    then the in-memory state is set to a low post-collection value.
    Returns the current fill state snapshot.
    """
    for bin_id in BINS:
        # Simulate gradual waste accumulation (+2 to +8% per 5-second cycle)
        increment = random.randint(2, 8)
        fill_state[bin_id] = min(100, fill_state[bin_id] + increment)

        if fill_state[bin_id] >= 95:
            # Collection event: log a 0% reading to the database
            # so the dashboard reflects the reset immediately
            print(f"  [COLLECTED] {bin_id} emptied at {fill_state[bin_id]}% — writing reset to DB")
            insert_reading(bin_id, 0)
            fill_state[bin_id] = random.randint(0, 5)

        # Record the current (post-event) fill level
        insert_reading(bin_id, fill_state[bin_id])

    return fill_state.copy()


if __name__ == "__main__":
    create_tables()  # Creates schema + seeds bin_master if not already done

    print("Simulation started... (CTRL+C to stop)")
    print(f"Initial fill states: {fill_state}\n")

    cycle = 0
    try:
        while True:
            cycle += 1
            readings = simulate_cycle()

            print(f"--- Cycle {cycle} ---")
            for bin_id, level in readings.items():
                print(f"  {bin_id}: {level}%")
            print()

            # Prune old telemetry rows every 10 cycles to cap DB size
            if cycle % 10 == 0:
                prune_old_readings(keep_last_n=500)
                print("  [DB] Telemetry pruned — keeping last 500 readings.\n")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\nSimulation stopped safely.")