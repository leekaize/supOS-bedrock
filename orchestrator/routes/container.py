"""Container management API routes"""

from datetime import datetime
from flask import Blueprint, jsonify

from auth import require_auth
from containers import (
    get_container_list,
    container_action,
    restart_all_services,
    create_backup
)

container_bp = Blueprint('container', __name__)

@container_bp.route('/api/supos/status')
@require_auth
def supos_status():
    """Get status of all containers"""
    try:
        containers = get_container_list(exclude_orchestrator=True)
        return jsonify({
            'containers': containers,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@container_bp.route('/api/supos/restart', methods=['POST'])
@require_auth
def restart_supos():
    """Restart all services"""
    result = restart_all_services()

    if result["success"]:
        return jsonify({"success": True, "message": result["message"]})
    else:
        return jsonify({"success": False, "error": result["error"]}), 500

@container_bp.route('/api/supos/container/<container_id>/<action>', methods=['POST'])
@require_auth
def container_action_route(container_id, action):
    """Execute action on specific container"""
    result = container_action(container_id, action)

    if result["success"]:
        return jsonify({"success": True})
    else:
        return jsonify({"error": result["error"]}), 500

@container_bp.route('/api/supos/backup', methods=['POST'])
@require_auth
def create_backup_route():
    """Create system backup"""
    try:
        result = create_backup()
        return jsonify({"success": True, "backup_path": result["backup_path"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@container_bp.route('/api/container/<container_name>/update', methods=['POST'])
@require_auth
def update_container_route(container_name):
    """Update container to recommended version - EXACT original implementation"""
    import docker
    import os
    import subprocess

    from containers import fetch_recommended_versions, parse_image_tag
    from config import WORKSPACE

    client = docker.from_env()

    try:
        container = client.containers.get(container_name)
        current_image = container.image.tags[0] if container.image.tags else None

        if not current_image:
            return jsonify({'error': 'Cannot determine current image'}), 400

        image_name, current_tag = parse_image_tag(current_image)
        recommended = fetch_recommended_versions()

        recommended_tag = None
        for rec_name, rec_tag in recommended.items():
            rec_image_name = rec_name.split('/')[-1].lower()
            image_short_name = image_name.split('/')[-1].lower()

            if image_short_name == rec_image_name:
                recommended_tag = rec_tag
                break

        if not recommended_tag:
            return jsonify({'error': 'No recommended version found'}), 404

        new_image = f"{image_name}:{recommended_tag}"

        # Determine compose file based on resource spec
        env_file = os.path.join(WORKSPACE, '.env')
        resource_spec = '2'
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('OS_RESOURCE_SPEC='):
                        resource_spec = line.strip().split('=')[1]
                        break

        compose_file = f"{WORKSPACE}/docker-compose-8c16g.yml" if resource_spec == '2' else f"{WORKSPACE}/docker-compose-4c8g.yml"

        # Create temporary override file
        override_file = f"{WORKSPACE}/docker-compose.update-{container_name}.yml"
        override_content = f"""services:
  {container_name}:
    image: {new_image}
"""

        with open(override_file, 'w') as f:
            f.write(override_content)

        try:
            # Apply override with full compose context
            result = subprocess.run(
                [
                    'docker', 'compose',
                    '--project-name', 'supos',
                    '--env-file', env_file,
                    '-f', compose_file,
                    '-f', override_file,
                    'up', '-d', container_name
                ],
                cwd=WORKSPACE,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return jsonify({
                    'error': f'Update failed: {result.stderr}',
                    'stdout': result.stdout
                }), 500

            return jsonify({
                'success': True,
                'container': container_name,
                'old_version': current_tag,
                'new_version': recommended_tag,
                'message': f'Updated {container_name} from {current_tag} to {recommended_tag}'
            })

        finally:
            if os.path.exists(override_file):
                os.remove(override_file)

    except docker.errors.NotFound:
        return jsonify({'error': f'Container {container_name} not found'}), 404
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
