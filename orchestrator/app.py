#!/usr/bin/env python3
"""supOS-bedrock Orchestrator - Main Application"""

import os
from datetime import timedelta
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

# Import all blueprints
from routes import (
    setup_bp,
    install_bp,
    auth_routes_bp,
    container_bp,
    version_bp,
    backup_bp
)

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')

# Session configuration
SECRET_KEY_FILE = '/app/config/secret.key'
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = os.urandom(24).hex()
    os.makedirs(os.path.dirname(SECRET_KEY_FILE), exist_ok=True)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(app.secret_key)

app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_NAME='orchestrator_session'
)

# Enable CORS
CORS(app, supports_credentials=True)

# Register blueprints
app.register_blueprint(setup_bp)
app.register_blueprint(install_bp)
app.register_blueprint(auth_routes_bp)
app.register_blueprint(container_bp)
app.register_blueprint(version_bp)
app.register_blueprint(backup_bp)

# Static file routes
@app.route('/')
def index():
    """Serve React frontend"""
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def catch_all(path):
    """Catch-all for React router"""
    if os.path.exists(os.path.join('static', path)):
        return send_from_directory('static', path)
    return send_from_directory('static', 'index.html')

@app.route('/api/health')
def health():
    """Health check endpoint"""
    from config import is_setup_complete
    return jsonify({
        "status": "ok",
        "setup_complete": is_setup_complete()
    })

from backup_scheduler import backup_scheduler
backup_scheduler.load_schedule()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
