import os
import time
import math
import argparse

import psutil
import requests

from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv(
    "CARBONTRACK_API_URL", ""
).rstrip("/")

TOKEN = os.getenv(
    "CARBONTRACK_DEVICE_TOKEN", ""
)

INTERVAL = max(
    30,
    int(os.getenv(
        "CARBONTRACK_INTERVAL_SECONDS", "300"
    ))
)

SAMPLE_SECONDS = 5

IDLE_WATTS = float(os.getenv(
    "CARBONTRACK_IDLE_WATTS", "0"
))

LOAD_WATTS = float(os.getenv(
    "CARBONTRACK_LOAD_WATTS", "0"
))


def collect():

    duration = 0.0
    energy_wh = 0.0
    cpu_weighted = 0.0
    memory_weighted = 0.0

    while duration < INTERVAL:

        sample = min(
            SAMPLE_SECONDS,
            INTERVAL - duration
        )

        started = time.monotonic()
        wall_started = time.time()

        cpu = psutil.cpu_percent(
            interval=sample
        )

        elapsed = (
            time.monotonic() - started
        )

        wall_elapsed = (
            time.time() - wall_started
        )

        # Discard unusually long samples,
        # including likely sleep/resume gaps.

        if max(elapsed, wall_elapsed) > sample + 3:
            print("Interrupted sample skipped.")
            continue

        if elapsed <= 0:
            continue

        memory = (
            psutil.virtual_memory().used
            / (1024 * 1024)
        )

        estimated_watts = (
            IDLE_WATTS
            + (LOAD_WATTS - IDLE_WATTS)
            * (cpu / 100)
        )

        energy_wh += (
            estimated_watts * elapsed / 3600
        )

        duration += elapsed

        cpu_weighted += cpu * elapsed

        memory_weighted += memory * elapsed

    return {
        "duration_seconds": round(duration, 2),

        "cpu_percent": round(
            cpu_weighted / duration, 2
        ),

        "memory_mb": round(
            memory_weighted / duration, 2
        ),

        "energy_kwh": round(
            energy_wh / 1000, 9
        ),

        "measurement_type": "estimated"
    }


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once",
        action="store_true"
    )

    args = parser.parse_args()

    if not API_URL.startswith("https://"):
        raise SystemExit(
            "Configure the HTTPS CarbonTrack URL."
        )

    if not TOKEN:
        raise SystemExit(
            "Configure your device token."
        )

    if not (
        math.isfinite(IDLE_WATTS)
        and math.isfinite(LOAD_WATTS)
        and 0 < IDLE_WATTS <= LOAD_WATTS <= 5000
    ):
        raise SystemExit(
            "Configure a valid device power profile."
        )

    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json"
    }

    print("CarbonTrack Agent started.")
    print("Measurement mode: Estimated")
    print("Idle power:", IDLE_WATTS, "W")
    print("Load power:", LOAD_WATTS, "W")
    print("Reporting interval:", INTERVAL, "seconds")

    with requests.Session() as session:

        while True:

            payload = collect()

            print("Collected:", payload)

            try:

                response = session.post(
                    API_URL + "/api/telemetry",
                    json=payload,
                    headers=headers,
                    timeout=15,
                    allow_redirects=False
                )

                if response.status_code in (401, 403):
                    raise SystemExit(
                        "Device token invalid or revoked."
                    )

                if response.status_code != 201:
                    print(
                        "Unexpected HTTP status:",
                        response.status_code
                    )
                else:
                    print(
                        "Telemetry accepted:",
                        response.json()
                    )

            except requests.RequestException as exc:

                print("Upload failed:", exc)

            if args.once:
                break


if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("\nCarbonTrack Agent stopped.")