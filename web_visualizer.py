"""
Bomberman+ Web Visualizer

Real-time 2D arena visualization using Flask + WebSocket
Shows live game state with color-coded entities

Usage:
    python3 web_visualizer.py
    
Then open: http://localhost:5000

Author: Bomberman AI
Date: 2025-12-20
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import json
import threading
import queue
import requests
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "https://games-test.datsteam.dev"
TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
POLL_INTERVAL = 2.0

app = Flask(__name__)
CORS(app)

# Shared state
game_state = None
state_lock = threading.Lock()
last_update = None


# ============================================================================
# API POLLING
# ============================================================================

def fetch_game_state():
    """Fetch game state from server continuously"""
    global game_state, last_update
    
    headers = {
        "X-Auth-Token": TOKEN,
        "Content-Type": "application/json"
    }
    
    while True:
        try:
            response = requests.get(
                f"{BASE_URL}/api/arena",
                headers=headers,
                timeout=2
            )
            
            if response.status_code == 200:
                with state_lock:
                    game_state = response.json()
                    last_update = datetime.now().isoformat()
                print(f"[Fetch] Updated at {last_update}")
            else:
                print(f"[Fetch] HTTP {response.status_code}")
        
        except Exception as e:
            print(f"[Fetch] Error: {e}")
        
        threading.Event().wait(POLL_INTERVAL)


# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def index():
    """Serve HTML page"""
    return render_template('arena.html')


@app.route('/api/state')
def get_state():
    """Return current game state as JSON"""
    with state_lock:
        if game_state is None:
            return jsonify({"error": "No state yet"}), 503
        
        return jsonify({
            "state": game_state,
            "timestamp": last_update
        })


@app.route('/api/health')
def health():
    """Health check"""
    with state_lock:
        status = "ok" if game_state else "loading"
    return jsonify({"status": status, "timestamp": last_update})


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Start background fetcher
    fetch_thread = threading.Thread(target=fetch_game_state, daemon=True)
    fetch_thread.start()
    
    print("=" * 70)
    print("BOMBERMAN+ WEB VISUALIZER")
    print(f"Server: {BASE_URL}")
    print("=" * 70)
    print("\nOpen http://localhost:5000 in your browser")
    print("\nFetching game state...")
    
    # Start Flask
    app.run(host='127.0.0.1', port=5000, debug=False)
