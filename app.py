from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__, static_folder='static')
CORS(app)

# In-memory storage for rowing data
# In a real application, this would be stored in a database
rowers_data = {}

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')

@app.route('/api/rowers', methods=['GET'])
def get_rowers():
    """Get all rowers and their current data"""
    return jsonify({
        'rowers': rowers_data,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/rowers/<rower_id>', methods=['GET'])
def get_rower(rower_id):
    """Get specific rower data"""
    if rower_id in rowers_data:
        return jsonify({
            'rower': rowers_data[rower_id],
            'timestamp': datetime.now().isoformat()
        })
    return jsonify({'error': 'Rower not found'}), 404

@app.route('/api/rowers/<rower_id>/update', methods=['POST'])
def update_rower(rower_id):
    """Update rower data (for testing/simulation)"""
    from flask import request
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Initialize rower data if not exists
    if rower_id not in rowers_data:
        rowers_data[rower_id] = {
            'id': rower_id,
            'name': data.get('name', f'Rower {rower_id}'),
            'distance': 0,
            'time': 0,
            'split': '0:00.0',
            'strokeRate': 0,
            'watts': 0,
            'calories': 0
        }
    
    # Update with provided data
    rowers_data[rower_id].update(data)
    rowers_data[rower_id]['lastUpdate'] = datetime.now().isoformat()
    
    return jsonify({
        'success': True,
        'rower': rowers_data[rower_id]
    })

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'rowers_count': len(rowers_data)
    })

if __name__ == '__main__':
    # Create static directory if it doesn't exist
    if not os.path.exists('static'):
        os.makedirs('static')
    
    # Run the Flask server
    # host='0.0.0.0' allows access from other devices on the network
    app.run(host='0.0.0.0', port=5000, debug=True)
