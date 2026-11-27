# CarbonTrack endpoint agent

Supports Windows, Linux and macOS with Python 3.10+.

1. Enroll a device from CarbonTrack → Devices & agents.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, then set the HTTPS app URL and the one-time device token.
4. Run `python agent.py --once` to test, then `python agent.py` for periodic telemetry.

The agent reports CPU percentage and memory usage as observations. It sends zero energy because generic CPU/RAM readings are not a validated electricity measurement. Protect `.env`; revoke the device if its token is exposed.
