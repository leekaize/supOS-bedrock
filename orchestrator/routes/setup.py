"""Setup wizard API routes"""

import os
import docker
from flask import Blueprint, jsonify, request

from config import load_config, update_env_file, WORKSPACE

setup_bp = Blueprint('setup', __name__)
client = docker.from_env()

@setup_bp.route('/api/setup/status')
def setup_status():
    """Get setup completion status and config"""
    from config import is_setup_complete
    config = load_config()
    return jsonify({
        "setup_complete": is_setup_complete(),
        "config": config
    })

@setup_bp.route('/api/setup/validate', methods=['POST'])
def validate_setup():
    """Validate system prerequisites"""
    try:
        issues = []
        warnings = []

        try:
            client.ping()
        except:
            issues.append("Docker socket unavailable")

        volumes_path = os.getenv("VOLUMES_PATH", "/volumes/supos/data")
        if not os.path.exists(volumes_path):
            issues.append(f"Volumes path missing: {volumes_path}")

        return jsonify({
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        })
    except Exception as e:
        return jsonify({"valid": False, "issues": [str(e)], "warnings": []}), 500

@setup_bp.route('/api/config/volumes-path')
def get_volumes_path():
    """Get volumes path and mount status"""
    try:
        path = os.getenv("VOLUMES_PATH", "/volumes/supos/data")
        return jsonify({"path": path, "mounted": os.path.exists(path)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@setup_bp.route('/api/config/detected-ips', methods=['GET'])
def get_detected_ips():
    """Get detected host IP addresses"""
    try:
        host_ips_raw = os.environ.get('HOST_IPS', '').strip()
        detected_ips = host_ips_raw.split() if host_ips_raw else []

        if '127.0.0.1' not in detected_ips:
            detected_ips.insert(0, '127.0.0.1')

        return jsonify({
            'detected_ips': detected_ips,
            'default_port': '8088'
        })
    except Exception as e:
        return jsonify({
            'detected_ips': ['127.0.0.1'],
            'default_port': '8088',
            'error': str(e)
        }), 500

@setup_bp.route('/api/config/check-volume', methods=['GET'])
def check_volume():
    """Check volume mount status and disk space"""
    try:
        volumes_path = '/volumes/supos/data'
        exists = os.path.exists(volumes_path)

        if exists:
            writable = os.access(volumes_path, os.W_OK)
            stat = os.statvfs(volumes_path)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
            sufficient = free_gb >= 20
        else:
            writable = False
            free_gb = total_gb = 0
            sufficient = False

        return jsonify({
            'path': volumes_path,
            'mounted': exists,
            'writable': writable,
            'free_gb': round(free_gb, 2),
            'total_gb': round(total_gb, 2),
            'sufficient': sufficient
        })
    except Exception as e:
        return jsonify({'mounted': False, 'error': str(e)}), 500

@setup_bp.route('/api/config/update', methods=['POST'])
def update_config():
    """Update network configuration in .env"""
    try:
        data = request.get_json()

        ip_address = data.get('ip_address', '').strip()
        port = data.get('entrance_port', '8088').strip()
        resource_spec = data.get('resource_spec', '1')

        if not ip_address:
            return jsonify({'success': False, 'error': 'IP address required'}), 400

        is_loopback = ip_address in ['127.0.0.1', 'localhost']

        updates = {
            'ENTRANCE_DOMAIN': ip_address,
            'ENTRANCE_PORT': port,
            'OS_RESOURCE_SPEC': resource_spec,
            'OS_AUTH_ENABLE': 'false' if is_loopback else 'true',
            'VOLUMES_PATH': '/volumes/supos/data'
        }

        update_env_file(updates)

        return jsonify({
            'success': True,
            'loopback_warning': is_loopback
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@setup_bp.route('/api/apps/list')
def list_apps():
    """List available optional apps - EXACT original implementation"""
    try:
        env_file = os.path.join(WORKSPACE, '.env')
        resource_spec = '2'

        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('OS_RESOURCE_SPEC='):
                        resource_spec = line.strip().split('=')[1]
                        break

        base_apps = [
            {'id': 'grafana', 'name': 'Grafana', 'description': 'Metrics visualization and monitoring dashboards', 'icon': '📊', 'category': 'monitoring'},
            {'id': 'minio', 'name': 'MinIO', 'description': 'S3-compatible object storage for data and backups', 'icon': '🗄️', 'category': 'storage'},
            {'id': 'mcpclient', 'name': 'MCP Client', 'description': 'Model Context Protocol client for AI integrations', 'icon': '🤖', 'category': 'ai'}
        ]

        extended_apps = [
            {'id': 'elk', 'name': 'ELK Stack', 'description': 'Elasticsearch, Logstash, Kibana for log analytics', 'icon': '🔍', 'category': 'logging', 'requires_high_resource': True},
            {'id': 'gitea', 'name': 'Gitea', 'description': 'Self-hosted Git service for version control', 'icon': '🔀', 'category': 'devops', 'requires_high_resource': True}
        ]

        apps = base_apps + extended_apps

        return jsonify({
            'apps': apps,
            'resource_spec': resource_spec,
            'spec_name': '8c16g (High Resource)' if resource_spec == '2' else '4c8g (Standard)'
        })

    except Exception as e:
        return jsonify({'apps': [], 'error': str(e)}), 500
