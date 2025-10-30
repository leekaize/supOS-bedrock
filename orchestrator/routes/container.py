"""Container management API routes with optional apps support"""

import os
import subprocess
from datetime import datetime
from flask import Blueprint, jsonify, request

from auth import require_auth
from containers import (
    get_container_list,
    container_action,
    restart_all_services,
    create_backup
)
from config import WORKSPACE, read_env_file

container_bp = Blueprint('container', __name__)

# Core apps that are always installed
CORE_APPS = [
    'postgresql', 'keycloak', 'emqx', 'kong',
    'backend', 'frontend', 'nodered', 'portainer',
    'chat2db', 'tsdb'
]

# Optional apps with their profiles
OPTIONAL_APPS = [
    {
        'id': 'grafana',
        'name': 'Grafana',
        'description': 'Metrics visualization and monitoring',
        'icon': '📊',
        'profile': 'grafana',
        'requires_high_resource': False
    },
    {
        'id': 'minio',
        'name': 'MinIO',
        'description': 'S3-compatible object storage',
        'icon': '🗄️',
        'profile': 'minio',
        'requires_high_resource': False
    },
    {
        'id': 'mcpclient',
        'name': 'MCP Client',
        'description': 'AI integrations via Model Context Protocol',
        'icon': '🤖',
        'profile': 'mcpclient',
        'requires_high_resource': False
    },
    {
        'id': 'elk',
        'name': 'ELK Stack',
        'description': 'Elasticsearch, Logstash, Kibana for logs',
        'icon': '🔍',
        'profile': 'elk',
        'requires_high_resource': True
    },
    {
        'id': 'gitea',
        'name': 'Gitea',
        'description': 'Self-hosted Git service',
        'icon': '🔀',
        'profile': 'gitea',
        'requires_high_resource': True
    }
]

def get_installed_profiles():
    """Read active-services.txt to get currently installed optional apps"""
    active_services_file = f"{WORKSPACE}/../volumes/supos/data/backend/system/active-services.txt"

    if not os.path.exists(active_services_file):
        return []

    try:
        with open(active_services_file, 'r') as f:
            content = f.read().strip()
            # First line contains comma-separated services
            if content:
                services = content.split('\n')[0].split(',')
                return [s.strip() for s in services if s.strip()]
    except Exception as e:
        print(f"Error reading active services: {e}")

    return []

def get_resource_spec():
    """Get current resource specification from .env"""
    env_vars = read_env_file()
    return env_vars.get('OS_RESOURCE_SPEC', '2')

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

@container_bp.route('/api/supos/apps/optional')
@require_auth
def get_optional_apps():
    """Get list of optional apps with install status"""
    try:
        installed_profiles = get_installed_profiles()
        resource_spec = get_resource_spec()
        containers = get_container_list(exclude_orchestrator=True)

        # Map container names to profiles
        container_map = {c['name']: c for c in containers}

        apps_status = []
        for app in OPTIONAL_APPS:
            # Check if app is available based on resource spec
            available = not (resource_spec == '1' and app['requires_high_resource'])

            # Check if profile is in active services
            installed = app['profile'] in installed_profiles

            # Find matching container
            container = None
            for c in containers:
                if app['id'] in c['name'].lower() or app['profile'] in c['name'].lower():
                    container = c
                    break

            apps_status.append({
                'id': app['id'],
                'name': app['name'],
                'description': app['description'],
                'icon': app['icon'],
                'profile': app['profile'],
                'requires_high_resource': app['requires_high_resource'],
                'available': available,
                'installed': installed,
                'status': container['status'] if container else 'not_installed',
                'container_name': container['name'] if container else None,
                'current_version': container.get('current_version') if container else None,
                'update_available': container.get('update_available', False) if container else False
            })

        return jsonify({
            'apps': apps_status,
            'resource_spec': resource_spec,
            'spec_name': '8c16g (High Resource)' if resource_spec == '2' else '4c8g (Standard)'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@container_bp.route('/api/supos/apps/optional/<app_id>/install', methods=['POST'])
@require_auth
def install_optional_app(app_id):
    """Install an optional app by adding its profile and running docker compose"""
    try:
        # Find the app
        app = next((a for a in OPTIONAL_APPS if a['id'] == app_id), None)
        if not app:
            return jsonify({'error': 'App not found'}), 404

        # Check resource requirements
        resource_spec = get_resource_spec()
        if resource_spec == '1' and app['requires_high_resource']:
            return jsonify({'error': 'This app requires 8c16g resources'}), 400

        # Get current installed profiles
        installed_profiles = get_installed_profiles()

        # Add the new profile if not already there
        if app['profile'] not in installed_profiles:
            installed_profiles.append(app['profile'])

        # Update active-services.txt
        active_services_file = f"{WORKSPACE}/../volumes/supos/data/backend/system/active-services.txt"
        os.makedirs(os.path.dirname(active_services_file), exist_ok=True)

        # Write updated services
        services_line = ','.join(installed_profiles)
        profile_args = ' '.join([f'--profile {p}' for p in installed_profiles if p not in CORE_APPS])

        with open(active_services_file, 'w') as f:
            f.write(f"{services_line}\n{profile_args}\n")

        # Determine compose file
        compose_file = f"{WORKSPACE}/docker-compose-8c16g.yml" if resource_spec == '2' else f"{WORKSPACE}/docker-compose-4c8g.yml"

        # Run docker compose with the new profile
        cmd = [
            'docker', 'compose',
            '--env-file', f'{WORKSPACE}/.env',
            '--project-name', 'supos',
            '--profile', app['profile'],
            '-f', compose_file,
            'up', '-d'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE)

        if result.returncode != 0:
            return jsonify({
                'success': False,
                'error': f"Failed to start {app['name']}",
                'details': result.stderr
            }), 500

        return jsonify({
            'success': True,
            'message': f"{app['name']} installation started",
            'app_id': app_id
        })

    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@container_bp.route('/api/supos/apps/optional/<app_id>/uninstall', methods=['POST'])
@require_auth
def uninstall_optional_app(app_id):
    """Uninstall an optional app by removing its profile and stopping containers"""
    try:
        # Find the app
        app = next((a for a in OPTIONAL_APPS if a['id'] == app_id), None)
        if not app:
            return jsonify({'error': 'App not found'}), 404

        # Get current installed profiles
        installed_profiles = get_installed_profiles()

        # Remove the profile
        if app['profile'] in installed_profiles:
            installed_profiles.remove(app['profile'])

        # Update active-services.txt
        active_services_file = f"{WORKSPACE}/../volumes/supos/data/backend/system/active-services.txt"

        services_line = ','.join(installed_profiles)
        profile_args = ' '.join([f'--profile {p}' for p in installed_profiles if p not in CORE_APPS])

        with open(active_services_file, 'w') as f:
            f.write(f"{services_line}\n{profile_args}\n")

        # Find and stop containers for this app using direct docker commands
        import docker
        client = docker.from_env()

        containers_removed = []
        for container in client.containers.list(all=True):
            # Match by app name pattern (e.g., grafana in container name)
            if app['id'].lower() in container.name.lower():
                try:
                    container.stop(timeout=10)
                    container.remove()
                    containers_removed.append(container.name)
                except Exception as e:
                    return jsonify({
                        'success': False,
                        'error': f"Failed to remove container {container.name}",
                        'details': str(e)
                    }), 500

        if not containers_removed:
            return jsonify({
                'success': False,
                'error': f"No containers found for {app['name']}"
            }), 404

        return jsonify({
            'success': True,
            'message': f"{app['name']} has been uninstalled",
            'app_id': app_id
        })

    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

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
