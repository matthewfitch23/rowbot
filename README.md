# rowbot
Realtime display board for one or more C2 rowers

## Overview
Rowbot is a Flask-based web application that provides a real-time display board for monitoring rowing data from Concept2 (C2) rowing machines. The application features a Python Flask server API and an interactive web interface.

## Features
- 🚣 Real-time display of rowing metrics
- 📊 Multi-rower support
- 🎨 Beautiful, responsive web interface
- 🔄 Auto-refreshing data display
- 🧪 Built-in simulation mode for testing

## Rowing Metrics Displayed
- Distance (meters)
- Time (elapsed)
- Split (500m pace)
- Stroke Rate (strokes per minute)
- Power (Watts)
- Calories

## Setup

### Prerequisites
- Python 3.7 or higher
- macOS (or Linux/Windows with minor adjustments)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/matthewfitch23/rowbot.git
cd rowbot
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Start the Flask server:
```bash
python app.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

The server will run on `0.0.0.0:5000`, making it accessible from other devices on your local network.

### Accessing from Other Devices
To access the display from other devices on your network (e.g., tablets, phones):
1. Find your Mac's local IP address (System Preferences → Network)
2. On the other device, navigate to `http://YOUR_MAC_IP:5000`

## API Endpoints

### GET /api/health
Health check endpoint to verify the server is running.

### GET /api/rowers
Get all rowers and their current data.

### GET /api/rowers/<rower_id>
Get specific rower data by ID.

### POST /api/rowers/<rower_id>/update
Update or create rower data.

**Request Body:**
```json
{
  "name": "Rower Name",
  "distance": 1000,
  "time": 180,
  "split": "1:30.0",
  "strokeRate": 24,
  "watts": 200,
  "calories": 50
}
```

## Demo/Simulation Mode

The web interface includes built-in simulation controls for testing:
- **Add Simulated Rower**: Creates a new virtual rower with random name
- **Start Simulation**: Begins automatic data updates for all rowers
- **Stop Simulation**: Pauses the simulation
- **Refresh Now**: Manually refresh the display

## Architecture

### Backend (Flask)
- `app.py`: Main Flask application with API endpoints
- In-memory data storage (can be extended to use a database)
- CORS enabled for cross-origin requests

### Frontend (Static Web Page)
- `static/index.html`: Single-page application
- Responsive design with gradient background
- Auto-refreshing every 2 seconds
- Interactive controls for simulation

## Future Enhancements
- Connect to real C2 rowing machines via PM5 monitors
- Database persistence for historical data
- User authentication and profiles
- Workout history and analytics
- Comparison and leaderboard features

## License
MIT License - see LICENSE file for details
