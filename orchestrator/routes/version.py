"""Version management and update API routes"""

from flask import Blueprint, jsonify, request

from containers import (
    fetch_recommended_versions,
    compare_container_versions,
    update_container_version
)

version_bp = Blueprint('version', __name__)

@version_bp.route('/api/versions/manifest')
def get_versions_manifest():
    """Fetch recommended versions from GitHub"""
    try:
        recommended = fetch_recommended_versions()
        return jsonify({
            'recommended': recommended,
            'source': 'https://raw.githubusercontent.com/leekaize/supOS-bedrock/main/builds.yaml'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@version_bp.route('/api/versions/compare')
def compare_versions():
    """Compare current versions with recommended"""
    try:
        containers = compare_container_versions()
        return jsonify({
            'containers': containers,
            'timestamp': __import__('datetime').datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@version_bp.route('/api/versions/update', methods=['POST'])
def update_version():
    """Update container to recommended version"""
    try:
        data = request.json
        container_name = data.get('container_name')
        recommended_tag = data.get('recommended_tag')

        if not container_name or not recommended_tag:
            return jsonify({'error': 'Missing container_name or recommended_tag'}), 400

        result = update_container_version(container_name, recommended_tag)

        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 500

    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
