"""CarbonTrack agent: collects system observations, not direct electricity readings."""
import os, time, platform, socket, argparse
import psutil, requests
from dotenv import load_dotenv
load_dotenv()
API_URL = os.getenv("CARBONTRACK_API_URL", "").rstrip("/")
TOKEN = os.getenv("CARBONTRACK_DEVICE_TOKEN", "")
INTERVAL = max(30, int(os.getenv("CARBONTRACK_INTERVAL_SECONDS", "300")))

def collect():
    return {"duration_seconds": INTERVAL, "cpu_percent": round(psutil.cpu_percent(interval=1), 2),
            "memory_mb": round(psutil.virtual_memory().used / (1024 * 1024), 2),
            "energy_kwh": 0, "measurement_type": "estimated"}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--once", action="store_true"); args = parser.parse_args()
    if not API_URL.startswith("https://") and not API_URL.startswith("http://localhost"):
        raise SystemExit("Set CARBONTRACK_API_URL to your HTTPS CarbonTrack URL.")
    if not TOKEN: raise SystemExit("Set CARBONTRACK_DEVICE_TOKEN in environment or .env")
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    while True:
        try:
            response = requests.post(API_URL + "/api/telemetry", json=collect(), headers=headers, timeout=15)
            response.raise_for_status(); print("Telemetry accepted:", response.json())
        except requests.RequestException as exc: print("Upload failed:", exc)
        if args.once: break
        time.sleep(INTERVAL)
if __name__ == "__main__": main()
