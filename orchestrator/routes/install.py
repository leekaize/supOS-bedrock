"""Installation API routes"""

import os
import time
from flask import Blueprint, jsonify, request, Response

from installation import (
    start_installation,
    get_installation_status,
    read_install_logs,
    sanitize_log_line,
    INSTALL_LOG
)

install_bp = Blueprint('install', __name__)

@install_bp.route('/api/install/start', methods=['POST'])
def install_start():
    """Start installation process"""
    try:
        data = request.json
        admin_data = data.get('admin', {})
        network_data = data.get('network', {})
        selected_apps = data.get('selected_apps', [])

        result = start_installation(admin_data, network_data, selected_apps)

        return jsonify({
            "success": result["success"],
            "message": result["message"],
            "log_endpoint": "/api/install/logs/stream"
        })

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

@install_bp.route('/api/install/logs/stream')
def stream_logs():
    """Stream installation logs from specific line"""
    from_line = request.args.get('from', 0, type=int)

    log_data = read_install_logs(from_line)
    return jsonify(log_data)

@install_bp.route('/api/install/status')
def install_status():
    """Check if installation is running"""
    if os.path.exists(INSTALL_LOG):
        age = time.time() - os.path.getmtime(INSTALL_LOG)
        if age < 600:
            return jsonify({"installing": True, "log_age": age})
    return jsonify({"installing": False})

@install_bp.route('/api/install/logs')
def view_full_logs():
    """View full installation log"""
    if not os.path.exists(INSTALL_LOG):
        return "No installation log found.\nStart installation from the wizard.", 404

    with open(INSTALL_LOG, 'r') as f:
        lines = f.readlines()
        sanitized = [sanitize_log_line(line) for line in lines]
        return Response(''.join(sanitized), mimetype='text/plain')

@install_bp.route('/api/install/logs/tail')
def tail_logs():
    """Get last 100 lines of installation log"""
    if not os.path.exists(INSTALL_LOG):
        return jsonify({"logs": "", "exists": False}), 200

    try:
        with open(INSTALL_LOG, 'r') as f:
            lines = f.readlines()
            tail = ''.join(lines[-100:])
            return jsonify({"logs": tail, "exists": True, "total_lines": len(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
