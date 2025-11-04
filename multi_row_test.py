#!/usr/bin/env python3
import threading
import time
from typing import Dict, List
from flask import Flask, jsonify

try:
    import pyrow
except Exception as e:
    raise SystemExit("pyrow is required. Install with: pip install pyrow Flask") from e

POLL_HZ = 5  # meters update rate per second

app = Flask(__name__)

# Shared state
erg_ids: List[str] = []
meters: Dict[str, float] = {}
locks: Dict[str, threading.Lock] = {}
stop_flag = threading.Event()


def discover_rowers():
    """Find connected PM5s and return list of pyrow devices."""
    devices = pyrow.find()  # returns list of low-level usb device handles
    if not devices:
        return []
    rowers = []
    for dev in devices:
        try:
            r = pyrow.PyRow(dev)
            # Use PM5 serial as stable ID when available, else USB address string
            info = r.getPMInfo()  # includes 'Serial' for PM5
            rid = str(info.get("Serial") or info.get("SerialNumber") or dev.address)
            rowers.append((rid, r))
        except Exception:
            continue
    return rowers


def poller(rid: str, r: "pyrow.PyRow"):
    """Poll a single rower for distance meters."""
    while not stop_flag.is_set():
        try:
            mon = r.getMonitor()  # returns distance, time, etc.
            dist_m = float(mon.get("distance", 0.0))
            with locks[rid]:
                meters[rid] = dist_m
        except Exception:
            with locks[rid]:
                meters[rid] = meters.get(rid, 0.0)  # keep last value on error
        time.sleep(1.0 / POLL_HZ)


@app.route("/status")
def status():
    """Return current meters per rower."""
    with threading.Lock():
        data = [{"id": rid, "meters": meters.get(rid, 0.0)} for rid in erg_ids]
    return jsonify({"rowers": data, "poll_hz": POLL_HZ})


def main():
    # Discover and start threads
    discovered = discover_rowers()
    if not discovered:
        print("No PM5 rowers found over USB. Plug in up to 3 and re-run.")
        return

    for rid, r in discovered[:8]:  # supports up to 8
        erg_ids.append(rid)
        locks[rid] = threading.Lock()
        meters[rid] = 0.0
        t = threading.Thread(target=poller, args=(rid, r), daemon=True)
        t.start()
        print(f"Connected: {rid}")

    # Start Flask in main thread
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        stop_flag.set()
