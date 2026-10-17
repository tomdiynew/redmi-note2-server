#!/data/data/com.termux/files/usr/bin/python3
"""LAN status dashboard for the Redmi Note 2 mini server (runs in Termux).

GET /             dashboard page
GET /api/status   current readings (JSON)
GET /api/history  last 24h of 1-minute samples (JSON)

Root-only data (Wi-Fi SSID, IP, charge control) comes from ~/.phonestat.json,
written every 15s by the phonectl root service.
"""
import json
import os
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("WEBSTAT_PORT", "8080"))
HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_JSON = os.path.join(HOME, ".phonestat.json")
HIST_FILE = os.path.join(HOME, ".webstat_history.json")
BAT = "/sys/class/power_supply/battery"
# thermal zone type -> label. Redmi Note 2 (MediaTek) and Pixel 2 XL (Snapdragon 835).
THERMAL_NAMES = {"mtktscpu": "CPU", "mtktsbattery": "电池", "mtktsAP": "主板",
                 "mtktspmic": "电源芯片", "mtktswmt": "Wi-Fi 芯片",
                 "battery": "电池", "pm8998_tz": "电源芯片", "xo_therm": "主板", "usb_port_temp": "USB 口"}
CPU_ZONE_PREFIX = "tsens_tz_sensor"  # Snapdragon: CPU = hottest tsens sensor


def celsius(raw):
    """Zones report °C, deci-°C or milli-°C depending on the driver."""
    v = abs(raw)
    return raw / 1000 if v >= 1000 else raw / 10 if v >= 150 else raw


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def num(path, scale=1.0):
    v = read(path)
    try:
        return float(v) * scale
    except (TypeError, ValueError):
        return None


def getprop(name):
    try:
        return subprocess.run(["getprop", name], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def cpu_times():
    """(busy+idle, idle) jiffies. The MTK kernel's iowait counter is garbage
    (goes negative / astronomically large), so it is left out entirely."""
    with open("/proc/stat") as f:
        p = [int(x) for x in f.readline().split()[1:8]]
    user, nice, system, idle, _iowait, irq, softirq = p
    busy = user + nice + system + irq + softirq
    return busy + idle, idle


class Sampler:
    """Keeps CPU/network deltas between calls and a 24h minute history."""

    def __init__(self):
        self.lock = threading.Lock()
        self.prev_cpu = cpu_times()
        self.prev_net = (time.time(), *self.net_bytes())
        self.cpu_pct = 0.0
        self.net_rate = (0.0, 0.0)
        self.history = deque(maxlen=1440)
        try:
            with open(HIST_FILE) as f:
                self.history.extend(json.load(f))
        except (OSError, ValueError):
            pass

    @staticmethod
    def net_bytes():
        for line in read("/proc/net/dev", "").splitlines():
            if line.strip().startswith("wlan0:"):
                f = line.split(":", 1)[1].split()
                return int(f[0]), int(f[8])
        return 0, 0

    def tick(self):
        with self.lock:
            total, idle = cpu_times()
            dt, di = total - self.prev_cpu[0], idle - self.prev_cpu[1]
            if dt > 0:
                self.cpu_pct = round(100.0 * (dt - di) / dt, 1)
            self.prev_cpu = (total, idle)
            now, (rx, tx) = time.time(), self.net_bytes()
            el = now - self.prev_net[0]
            if el > 0.5:
                self.net_rate = (max(0, rx - self.prev_net[1]) / el, max(0, tx - self.prev_net[2]) / el)
                self.prev_net = (now, rx, tx)

    def record(self, st):
        with self.lock:
            self.history.append({"t": int(time.time()), "bat": st["battery"]["level"],
                                 "temp": st["temps"].get("CPU"), "cpu": st["cpu"]["usage_pct"]})

    def save(self):
        with self.lock:
            data = list(self.history)
        tmp = HIST_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, HIST_FILE)


sampler = Sampler()
STATIC = {"model": getprop("ro.product.model"), "android": getprop("ro.build.version.release"),
          "rom": getprop("ro.lineage.version") or getprop("ro.cm.version") or getprop("ro.build.display.id"),
          "kernel": os.uname().release, "arch": os.uname().machine}


def status():
    up = float(read("/proc/uptime", "0").split()[0])
    mem = {}
    for line in read("/proc/meminfo", "").splitlines():
        k, v = line.split(":", 1)
        mem[k] = int(v.split()[0]) * 1024
    vfs = os.statvfs(HOME)
    online = read("/sys/devices/system/cpu/online", "0")
    cores = []
    for part in online.split(","):
        a, _, b = part.partition("-")
        cores += range(int(a), int(b or a) + 1)
    freqs = {c: num(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_cur_freq", 1 / 1000) for c in cores}
    temps, tsens = {}, []
    for z in sorted(os.listdir("/sys/class/thermal")):
        if z.startswith("thermal_zone"):
            ztype = read(f"/sys/class/thermal/{z}/type", "")
            raw = num(f"/sys/class/thermal/{z}/temp")
            if raw is None:
                continue
            t = celsius(raw)
            if not -40 < t < 150:
                continue
            if ztype.startswith(CPU_ZONE_PREFIX):
                tsens.append(t)
            elif ztype in THERMAL_NAMES:
                temps[THERMAL_NAMES[ztype]] = round(t, 1)
    if tsens:
        temps["CPU"] = round(max(tsens), 1)
    try:
        with open(ROOT_JSON) as f:
            root = json.load(f)
        root["age_s"] = int(time.time() - root.get("ts", 0))
    except (OSError, ValueError):
        root = None
    load = read("/proc/loadavg", "0 0 0").split()[:3]
    return {
        "time": int(time.time()), "device": STATIC, "uptime_s": int(up),
        "cpu": {"usage_pct": sampler.cpu_pct, "load": [float(x) for x in load],
                "cores_online": len(cores),
                "cores_total": int(read("/sys/devices/system/cpu/possible", "0-0").split("-")[-1]) + 1,
                "freq_mhz": {str(c): round(v) for c, v in freqs.items() if v}},
        "temps": temps,
        "memory": {"total": mem.get("MemTotal"), "available": mem.get("MemAvailable", mem.get("MemFree"))},
        "storage": {"total": vfs.f_blocks * vfs.f_frsize, "free": vfs.f_bavail * vfs.f_frsize},
        "battery": {"level": num(f"{BAT}/capacity"), "status": read(f"{BAT}/status"),
                    "health": read(f"{BAT}/health"),
                    # MTK: batt_vol (mV), batt_temp (0.1 °C); Qualcomm: voltage_now (µV), temp (0.1 °C)
                    "voltage_mv": num(f"{BAT}/batt_vol") or num(f"{BAT}/voltage_now", 1 / 1000),
                    "temp_c": num(f"{BAT}/batt_temp", 0.1) or num(f"{BAT}/temp", 0.1),
                    "usb": read("/sys/class/power_supply/usb/online") == "1",
                    "ac": read("/sys/class/power_supply/ac/online") == "1"},
        "network": {"rx_bps": round(sampler.net_rate[0]), "tx_bps": round(sampler.net_rate[1]),
                    "rx_total": Sampler.net_bytes()[0], "tx_total": Sampler.net_bytes()[1]},
        "root": root,
    }


def tick_loop():
    """CPU/network rates are sampled on a fixed 5s clock, not per request:
    on this single-core 800 MHz phone a request's own work would dominate."""
    while True:
        time.sleep(5)
        sampler.tick()


def history_loop():
    n = 0
    while True:
        try:
            sampler.record(status())
            n += 1
            if n % 10 == 0:
                sampler.save()
        except Exception as e:  # never let the sampler thread die
            print("history error:", e, flush=True)
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            self._send(200, json.dumps(status(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path == "/api/history":
            with sampler.lock:
                data = list(sampler.history)
            self._send(200, json.dumps(data).encode(), "application/json")
        elif path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass  # keep the Termux log quiet


if __name__ == "__main__":
    threading.Thread(target=tick_loop, daemon=True).start()
    threading.Thread(target=history_loop, daemon=True).start()
    print(f"webstat listening on 0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
