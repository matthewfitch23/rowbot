#!/usr/bin/env python3
# app.py
#
# pip install flask pyusb pyrow waitress
#
# Run:
#   PM5_ADMIN_TOKEN="changeme" python app.py
# or (prod-ish):
#   waitress-serve --host=0.0.0.0 --port=5000 app:app
#
# Endpoints:
#   GET  /status                 -> live meters, devices
#   POST /adjust                 -> {device_key|all, delta, reason} with X-Admin-Token
#   GET  /fundraising_status     -> {amount}
#   POST /fundraising_set        -> {amount, reason} with X-Admin-Token
#   GET  /healthz                -> liveness
#
# Notes:
# - Snapshot + append-only event log for crash-safety.
# - Ignores negative deltas (device reset) and clamps spikes.
# - Countdown mode supported (adds absolute negative delta up to SANITY_MAX_DELTA).
# - Auto-reconnects devices; first read after (re)connect is baseline (no add).
# - Uses PM5 serial where available as stable device label.

import atexit
import json
import os
import signal
import sys
import threading
import time
from functools import wraps
from typing import Any

# --- Optional: comment out if you want to start UI elsewhere ---
# Serve index.html from ./public if you drop your big-screen file there.
from flask import Flask, abort, jsonify, request, send_from_directory

try:
    from pyrow import pyrow as c2  # requires libusb via pyusb underneath
except Exception as e:
    print("Warning: pyrow import failed. USB polling will not work:", e, file=sys.stderr)
    c2 = None

# -------------------- Config --------------------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
STATE_FILE = os.getenv("STATE_FILE", "pm5_state.json")
EVENT_LOG = os.getenv("EVENT_LOG", "pm5_events.ndjson")
ADMIN_TOKEN = os.getenv("PM5_ADMIN_TOKEN", "changeme")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))  # seconds
SAVE_INTERVAL = float(os.getenv("SAVE_INTERVAL", "5.0"))  # seconds
SANITY_MAX_DELTA = int(os.getenv("SANITY_MAX_DELTA", "100"))  # m/s per device
COUNTDOWN_SUPPORT = os.getenv("COUNTDOWN_SUPPORT", "1") == "1"  # add abs(neg_delta) when true

# -------------------- App / State --------------------
app = Flask(__name__)
state_lock = threading.Lock()

# State shape:
# {
#   "devices": {
#     "<key>": {
#         "label": "PM5-<serial or id>",
#         "last_device_meters": 123,
#         "cumulative": 4567,
#         "connected": true/false,
#         "last_seen": 1690000000.0
#     }, ...
#   },
#   "fundraising_amount": 0,   # integer pounds
#   "last_saved": 1690000000.0
# }
state: dict[str, Any] = {"devices": {}, "fundraising_amount": 0, "last_saved": None}


def fsync_append(path: str, line: str) -> None:
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def log_event(ev: dict) -> None:
    fsync_append(EVENT_LOG, json.dumps(ev, separators=(",", ":")) + "\n")


def save_state() -> None:
    with state_lock:
        state["last_saved"] = time.time()
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, separators=(",", ":"), sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATE_FILE)


def load_state() -> None:
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    state.update(data)
        except Exception as e:
            print("Warning: failed to load state:", e, file=sys.stderr)


def device_key_from_raw(raw) -> str:
    # pyrow.find() returns a device handle; stringify for a stable-ish key
    return str(raw)


def friendly_label(erg) -> str:
    # Best effort to extract a serial/label; fall back to repr
    try:
        info = erg.get_workout() or {}
        serial = info.get("serial") or info.get("device_serial")
        if serial:
            return f"PM5-{serial}"
    except Exception:
        pass
    return repr(erg)


def replay_events_into_state() -> None:
    """Rebuild cumulative totals from the append-only log."""
    if not os.path.exists(EVENT_LOG):
        return
    with state_lock:
        # Reset computed fields (keep fundraising from snapshot)
        # devices = state.get("devices", {})
        fundraising = state.get("fundraising_amount", 0)
        state.clear()
        state["devices"] = {}
        state["fundraising_amount"] = fundraising
        state["last_saved"] = None

    with open(EVENT_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            t = float(ev.get("t", time.time()))
            if "reading" in ev:
                key = ev.get("device")
                meters = int(ev["reading"])
                with state_lock:
                    dev = state["devices"].setdefault(
                        key,
                        {
                            "label": key,
                            "last_device_meters": None,
                            "cumulative": 0,
                            "connected": False,
                            "last_seen": 0.0,
                        },
                    )
                    last = dev["last_device_meters"]
                    if last is None:
                        delta = 0
                    else:
                        delta = meters - last
                        if delta < 0:
                            delta = min(-delta, SANITY_MAX_DELTA) if COUNTDOWN_SUPPORT else 0
                        elif delta > SANITY_MAX_DELTA:
                            delta = 0
                    dev["cumulative"] += int(delta)
                    dev["last_device_meters"] = meters
                    dev["last_seen"] = t
            elif "adjust_delta" in ev:
                key = ev.get("device")
                with state_lock:
                    dev = state["devices"].setdefault(
                        key,
                        {
                            "label": key,
                            "last_device_meters": None,
                            "cumulative": 0,
                            "connected": False,
                            "last_seen": 0.0,
                        },
                    )
                    dev["cumulative"] += int(ev["adjust_delta"])
                    dev["last_seen"] = t
            elif "fund_set" in ev:
                with state_lock:
                    state["fundraising_amount"] = int(ev["fund_set"])


# -------------------- Polling thread --------------------
stop_event = threading.Event()


def poll_loop():
    if c2 is None:
        print("pyrow unavailable; skipping USB polling loop.", file=sys.stderr)
        return

    erg_map = {}  # key -> PyRow
    last_save = time.time()

    while not stop_event.is_set():
        try:
            found = c2.find() or []
            found_keys = [device_key_from_raw(f) for f in found]

            # Connect new devices
            for raw in found:
                key = device_key_from_raw(raw)
                if key not in erg_map:
                    try:
                        erg = c2.PyErg(raw)
                        _ = erg.get_workout()  # probe
                        erg_map[key] = erg
                        with state_lock:
                            dev = state["devices"].setdefault(
                                key,
                                {
                                    "label": friendly_label(erg),
                                    "last_device_meters": None,
                                    "cumulative": 0,
                                    "connected": True,
                                    "last_seen": time.time(),
                                },
                            )
                            dev["connected"] = True
                            dev["last_seen"] = time.time()
                        print("Connected:", key)
                    except Exception as e:
                        print("Init fail", key, e, file=sys.stderr)

            # Mark disconnected
            for key in list(erg_map.keys()):
                if key not in found_keys:
                    print("Disconnected:", key)
                    with state_lock:
                        if key in state["devices"]:
                            state["devices"][key]["connected"] = False
                            state["devices"][key]["last_seen"] = time.time()
                    erg_map.pop(key, None)

            # Poll connected
            for key, erg in list(erg_map.items()):
                try:
                    data = erg.get_monitor() or {}
                    meters = int(data.get("distance") or 0)
                    now = time.time()
                    # log raw reading
                    log_event({"t": now, "device": key, "reading": meters})

                    with state_lock:
                        dev = state["devices"].setdefault(
                            key,
                            {
                                "label": friendly_label(erg),
                                "last_device_meters": None,
                                "cumulative": 0,
                                "connected": True,
                                "last_seen": now,
                            },
                        )
                        last = dev["last_device_meters"]
                        if last is None:
                            delta = 0
                        else:
                            delta = meters - last
                            if delta < 0:
                                delta = min(-delta, SANITY_MAX_DELTA) if COUNTDOWN_SUPPORT else 0
                            elif delta > SANITY_MAX_DELTA:
                                delta = 0
                        dev["cumulative"] += int(delta)
                        dev["last_device_meters"] = meters
                        dev["connected"] = True
                        dev["last_seen"] = now

                    # tiny console line
                    print(f"[{dev['label']}] device:{meters} cum:{dev['cumulative']}")

                except Exception as e:
                    print("Read error", key, e, file=sys.stderr)
                    with state_lock:
                        if key in state["devices"]:
                            state["devices"][key]["connected"] = False
                            state["devices"][key]["last_seen"] = time.time()
                    erg_map.pop(key, None)

            # periodic snapshot
            if time.time() - last_save >= SAVE_INTERVAL:
                save_state()
                last_save = time.time()

            stop_event.wait(POLL_INTERVAL)

        except Exception as e:
            print("Poll loop error:", e, file=sys.stderr)
            time.sleep(2)


# -------------------- Auth helper --------------------
def require_token(fn):
    @wraps(fn)
    def _inner(*args, **kwargs):
        tok = request.headers.get("X-Admin-Token")
        if not tok or tok != ADMIN_TOKEN:
            abort(401)
        return fn(*args, **kwargs)

    return _inner


# -------------------- HTTP Endpoints --------------------
@app.route("/status", methods=["GET"])
def http_status():
    with state_lock:
        connected = sum(1 for d in state["devices"].values() if d.get("connected"))
        return jsonify(
            {
                "connected_count": connected,
                "devices": state["devices"],
                "last_saved": state.get("last_saved"),
            }
        )


@app.route("/adjust", methods=["POST"])
@require_token
def http_adjust():
    body = request.get_json(force=True, silent=True) or {}
    device_key = body.get("device_key")
    delta = body.get("delta")
    reason = body.get("reason", "")
    who = body.get("by", "operator")
    if device_key is None or delta is None:
        return jsonify({"error": "device_key and delta required"}), 400
    try:
        delta = int(delta)
    except Exception:
        return jsonify({"error": "delta must be integer"}), 400

    now = time.time()
    with state_lock:
        if device_key == "all":
            for k, dev in state["devices"].items():
                dev["cumulative"] = int(dev.get("cumulative", 0) + delta)
                dev["last_seen"] = now
                log_event(
                    {
                        "t": now,
                        "device": k,
                        "adjust_delta": delta,
                        "by": who,
                        "reason": reason,
                    }
                )
            save_state()
            return jsonify({"ok": True, "applied_to": "all", "delta": delta})
        if device_key not in state["devices"]:
            return jsonify({"error": "device not found", "device_key": device_key}), 404
        dev = state["devices"][device_key]
        dev["cumulative"] = int(dev.get("cumulative", 0) + delta)
        dev["last_seen"] = now
        log_event(
            {
                "t": now,
                "device": device_key,
                "adjust_delta": delta,
                "by": who,
                "reason": reason,
            }
        )
        save_state()
        return jsonify({"ok": True, "device_key": device_key, "new_total": dev["cumulative"]})


@app.route("/fundraising_status", methods=["GET"])
def http_fund_status():
    with state_lock:
        return jsonify({"amount": int(state.get("fundraising_amount", 0))})


@app.route("/fundraising_set", methods=["POST"])
@require_token
def http_fund_set():
    body = request.get_json(force=True, silent=True) or {}
    amount = body.get("amount")
    reason = body.get("reason", "")
    if amount is None:
        return jsonify({"error": "amount required (integer, pounds)"}), 400
    try:
        amount = int(amount)
    except Exception:
        return jsonify({"error": "amount must be integer"}), 400
    with state_lock:
        state["fundraising_amount"] = amount
        log_event({"t": time.time(), "fund_set": amount, "reason": reason})
        save_state()
    return jsonify({"ok": True, "amount": amount})


@app.route("/healthz", methods=["GET"])
def http_healthz():
    return "ok", 200


# -------- Optional static hosting for your big-screen UI --------
# Put your index.html in ./public (the file you built in canvas)
@app.route("/")
def root_index():
    if os.path.exists("public/index.html"):
        return send_from_directory("public", "index.html")
    return "UI not found. Place index.html in ./public", 200


@app.route("/<path:path>")
def static_proxy(path):
    if os.path.exists(os.path.join("public", path)):
        return send_from_directory("public", path)
    abort(404)


# -------------------- Lifecycle --------------------
def start_threads():
    # Load snapshot then replay log (snapshot wins for fundraising_amount, log recomputes cumulative)
    load_state()
    replay_events_into_state()
    # Start poller
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    return t


def shutdown(*_):
    stop_event.set()
    try:
        save_state()
    except Exception:
        pass


atexit.register(shutdown)
signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# -------------------- Entrypoint --------------------
if __name__ == "__main__":
    start_threads()
    print(
        f"Serving on http://{HOST}:{PORT}  (admin token set: {'yes' if ADMIN_TOKEN != 'changeme' else 'NO – change PM5_ADMIN_TOKEN'})"
    )
    app.run(host=HOST, port=PORT, threaded=True)
else:
    # For waitress-serve / gunicorn
    start_threads()
