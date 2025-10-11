# Rowbot 🚣‍♂️

**Rowbot** is an open-source big-screen display + backend for Concept2 rower challenges and fundraising events.
It connects to multiple PM5 monitors, counts up total metres rowed in real time, and shows the results on a simple full-screen web page — perfect for gyms, CrossFit boxes, and charity “million-metre” events.

<img width="2311" height="1511" alt="Screenshot 2025-10-11 at 11 38 17" src="https://github.com/user-attachments/assets/f6694352-a800-49b6-a8d2-8cdf34bf3a68" />

---

## ✨ Features

- **Real-time metre tracking** across any number of Concept2 rowers (PM5).
- **Crash-safe state** with append-only log + periodic snapshots.
- **Handles edge cases**: disconnects, countdown workouts, resets, new devices mid-event.
- **Manual corrections**:
  - Add missed metres.
  - Override fundraising total.
- **Fundraising integration**: track amount raised alongside metres.
- **Web UI** (`./static/index.html`):
  - Big, high-contrast counter for gym screens.
  - Shows connected rowers and donation total.
  - Demo mode for testing without hardware.
- **Resilient Python server** (`./app.py`) with REST API.
- **MIT licensed** — free for anyone to use, modify, and share.

---

## 🚀 Quick start

### 1. Clone and set up

Rowbot is built for **Python 3.11**. We recommend [uv](https://github.com/astral-sh/uv) for fast installs.

    git clone https://github.com/yourname/rowbot.git
    cd rowbot
    uv venv
    source .venv/bin/activate
    uv pip install -r requirements.txt

### 2. Run the server

    PM5_ADMIN_TOKEN="supersecret" python app.py

### 3. Open the UI

Go to http://localhost:5000/ in a browser.
Put `static/index.html` up on a big screen to watch the metres tick up.

---

## 🔌 API endpoints

- **GET /status** → current totals & connected devices.
- **POST /adjust** → add metres manually.
  - Body: {"device_key":"all"|"PM5-...","delta":25,"reason":"..."}
- **GET /fundraising_status** → {"amount": 1234} (pounds).
- **POST /fundraising_set** → override fundraising total.
  - Body: {"amount": 5000, "reason":"manual correction"}

All mutating endpoints require header: X-Admin-Token: <PM5_ADMIN_TOKEN>

---

## 🖥️ Demo mode

Append `?demo=1` to the URL (e.g. http://localhost:5000/?demo=1) to simulate metres ticking up and random donations without any hardware.

---

## 📂 Project structure

    rowbot/
    ├── app.py              # Flask server & PM5 polling loop
    ├── requirements.txt    # Python dependencies
    ├── pyproject.toml      # Ruff + Black configuration
    ├── ruff.toml           # (optional, if you want overrides)
    └── static/
        └── index.html      # Full-screen web UI

---

## 🛠️ Requirements

- Python 3.11
- Concept2 rowers with **PM5 monitors** (USB)
- libusb installed on your system (for pyusb/pyrow)

---

## 🧹 Code style

We use **[Ruff](https://github.com/astral-sh/ruff)** for linting & import sorting, and **[Black](https://black.readthedocs.io/)** for formatting.

Check and fix:

    ruff check --fix .
    black .

Ruff is also configured to run `pyupgrade` rules for modern Python 3.11 syntax.

---

## 📝 License

MIT © 2025 Matthew Fitch
