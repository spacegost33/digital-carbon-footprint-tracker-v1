import math

DEVICE_PROFILES = {
    "smartphone": "Smartphone (charging)",
    "tablet": "Tablet (charging)",
    "smartwatch": "Smartwatch (charging)",
    "router": "Wi-Fi router",
    "modem": "Modem",
    "smart_tv": "Smart TV",
    "console": "Gaming console",
    "cctv": "CCTV camera",
    "iot": "IoT sensor",
    "raspberry_pi": "Raspberry Pi",
    "esp32": "ESP32",
    "monitor": "External monitor",
    "printer": "Printer",
    "speaker": "Smart speaker",
    "storage": "Network storage",
    "custom": "Other electronic device"
}


def estimate_device_energy(watts, hours, quantity=1):

    watts = float(watts)
    hours = float(hours)
    quantity = int(quantity)

    if not (
        math.isfinite(watts)
        and math.isfinite(hours)
        and 0 < watts <= 10000
        and 0 < hours <= 24
        and 1 <= quantity <= 1000
    ):
        raise ValueError(
            "Invalid power, duration or quantity."
        )

    energy_kwh = (
        watts * hours * quantity
    ) / 1000

    if energy_kwh > 10000:
        raise ValueError(
            "Energy exceeds the permitted limit."
        )

    return energy_kwh