"""Backup management API routes"""

import os
import json
from pathlib import Path
from flask import Blueprint, jsonify, request
from auth import require_auth
from backup_manager import backup_manager

backup_bp = Blueprint('backup', __name__)

CONFIG_FILE = Path("/volumes/supos/data/backend/system/backup_config.json")


def get_backup_config():
    """Read backup configuration"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"backup_path": "/volumes/supos/backups"}


def save_backup_config(config):
    """Save backup configuration"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


@backup_bp.route('/api/backup/config', methods=['GET'])
@require_auth
def get_config():
    """Get backup configuration"""
    try:
        config = get_backup_config()
        return jsonify({"success": True, **config})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@backup_bp.route('/api/backup/config', methods=['POST'])
@require_auth
def update_config():
    """Update backup configuration"""
    try:
        data = request.json
        backup_path = data.get('backup_path')

        if not backup_path:
            return jsonify({"error": "backup_path required"}), 400

        # Validate path exists
        if not os.path.exists(backup_path):
            return jsonify({"error": f"Path does not exist: {backup_path}"}), 400

        config = {"backup_path": backup_path}
        save_backup_config(config)

        # Reinitialize backup manager with new path
        backup_manager.update_path(backup_path)

        return jsonify({"success": True, "message": "Backup path updated"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@backup_bp.route('/api/backup/create', methods=['POST'])
@require_auth
def create_backup():
    """Trigger manual backup"""
    try:
        data = request.json or {}
        backup_name = data.get('name')

        result = backup_manager.create_backup(backup_name)
        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@backup_bp.route('/api/backup/list', methods=['GET'])
@require_auth
def list_backups():
    """Get all available backups"""
    try:
        backups = backup_manager.list_backups()
        return jsonify({
            "success": True,
            "backups": backups,
            "count": len(backups)
        })

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@backup_bp.route('/api/backup/restore', methods=['POST'])
@require_auth
def restore_backup():
    """Restore from backup archive - WARNING: Stops all services"""
    try:
        data = request.json
        archive_name = data.get('archive_name')

        if not archive_name:
            return jsonify({"error": "archive_name required"}), 400

        result = backup_manager.restore_backup(archive_name)
        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@backup_bp.route('/api/backup/delete', methods=['POST'])
@require_auth
def delete_backup():
    """Delete backup archive"""
    try:
        data = request.json
        archive_name = data.get('archive_name')

        if not archive_name:
            return jsonify({"error": "archive_name required"}), 400

        result = backup_manager.delete_backup(archive_name)
        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
