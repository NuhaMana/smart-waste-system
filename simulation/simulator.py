import random
import time
from database.db import (
    create_tables,
    insert_reading,
    log_collection_event,
    prune_old_readings,
    get_fill_rates,
)

BINS = ["BIN-001", "BIN-002", "BIN-003", "BIN-004", "BIN-005"]

# In-memory fill state — randomised at startup to simulate different starting conditions
fill_state = {bin_id: random.randint(10, 40) for bin_id in BINS}

# Per-bin fill rates — default 5 until loaded from bin_master after DB init
FILL_RATES = {bin_id: 5 for bin_id in BINS}


def simulate_cycle():
    """
    One simulation cycle (runs every 5 seconds).

    Each bin's fill level is incremented by its individual base fill_rate
    (loaded from bin_master) plus a small random variation of ±2%, simulating
    real-world sensor noise and uneven waste generation.

    If a bin reaches the collection threshold (>= 95%):
      - A collection event is written to the collection_events table.
      - The bin's fill level resets to a low value (0–5%) in memory.
      - The next telemetry insert reflects the post-collection level.
      - No spurious 0% row is mixed into the telemetry log.
    """
    for bin_id in BINS:
        base_rate = FILL_RATES.get(bin_id, 5)
        # ±2% noise around the base rate; never less than 1%
        increment = max(1, base_rate + random.randint(-2, 2))
        fill_state[bin_id] = min(100, fill_state[bin_id] + increment)

        if fill_state[bin_id] >= 95:
            print(
                f"  [COLLECTED] {bin_id} emptied at {fill_state[bin_id]}% "
                f"(base rate: {base_rate}%/cycle)"
            )
            # Write to collection_events table — separate from telemetry
            log_collection_event(bin_id, fill_state[bin_id])
            fill_state[bin_id] = random.randint(0, 5)

        # Record current fill level to telemetry (clean data only)
        insert_reading(bin_id, fill_state[bin_id])

    return fill_state.copy()


if __name__ == "__main__":
    create_tables()                    # Create schema + seed bin_master if needed
    FILL_RATES.update(get_fill_rates()) # Load per-bin rates from DB

    print("=" * 50)
    print("  Smart Waste IoT Simulator")
    print("  Press CTRL+C to stop")
    print("=" * 50)
    print(f"Fill rates loaded from DB: {FILL_RATES}")
    print(f"Initial fill states:       {fill_state}")
    print()

    cycle = 0
    try:
        while True:
            cycle += 1
            readings = simulate_cycle()

            print(f"--- Cycle {cycle} ---")
            for bin_id, level in readings.items():
                rate = FILL_RATES.get(bin_id, 5)
                bar  = "█" * (level // 10) + "░" * (10 - level // 10)
                print(f"  {bin_id} ({rate}%/cycle)  [{bar}]  {level}%")
            print()

            # Prune telemetry log every 10 cycles (keep last 500 rows)
            if cycle % 10 == 0:
                prune_old_readings(keep_last_n=500)
                print("  [DB] Telemetry pruned — oldest readings removed.\n")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\nSimulation stopped safely.")