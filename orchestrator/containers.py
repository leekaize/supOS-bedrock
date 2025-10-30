"""Docker container management and version control"""

import os
import re
import yaml
import subprocess
import docker
import requests
from packaging import version as pkg_version

from config import WORKSPACE

client = docker.from_env()

def get_container_list(exclude_orchestrator=True):
    """Get list of running containers

    Args:
        exclude_orchestrator: Exclude supos-bedrock container

    Returns:
        list: Container info dicts
    """
    containers = []
    for container in client.containers.list(all=True):
        if exclude_orchestrator and container.name == 'supos-bedrock':
            continue

        containers.append({
            'id': container.id[:12],
            'name': container.name,
            'status': container.status,
            'image': container.image.tags[0] if container.image.tags else 'unknown'
        })

    return containers

def container_action(container_id, action):
    """Execute action on container

    Args:
        container_id: Container ID
        action: 'start', 'stop', or 'restart'

    Returns:
        dict: {"success": bool, "error": str}
    """
    if action not in ['start', 'stop', 'restart']:
        return {"success": False, "error": "Invalid action"}

    try:
        container = client.containers.get(container_id)
        getattr(container, action)()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def restart_all_services():
    """Restart all services via docker compose

    Returns:
        dict: {"success": bool, "message": str, "error": str}
    """
    try:
        subprocess.run(
            ['docker', 'compose', 'restart'],
            cwd=WORKSPACE,
            check=True,
            capture_output=True
        )
        return {"success": True, "message": "Services restarted"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_backup():
    """Create backup of volumes and configs

    Returns:
        dict: {"success": bool, "backup_path": str}
    """
    from datetime import datetime

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = f"/workspace/backups/backup_{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)

    subprocess.run(['cp', '-r', '/workspace/mount', backup_dir], check=True)

    volumes_path = os.getenv('VOLUMES_PATH', '/volumes/supos/data')
    subprocess.run(['tar', '-czf', f"{backup_dir}/volumes.tar.gz", volumes_path])

    return {"success": True, "backup_path": backup_dir}

def fetch_recommended_versions():
    """Fetch recommended versions from GitHub manifest

    Returns:
        dict: {image_name: recommended_version}
    """
    github_url = 'https://raw.githubusercontent.com/leekaize/supOS-bedrock/main/builds.yaml'
    response = requests.get(github_url, timeout=10)

    if response.status_code != 200:
        raise Exception(f'GitHub fetch failed: {response.status_code}')

    manifest = yaml.safe_load(response.text)

    recommended = {}
    for img in manifest.get('images', []):
        image_name = f"{img['imagePath']}/{img['imageName']}"
        recommended[image_name] = str(img['imageTag'])

    for img in manifest.get('openImages', []):
        image_name = img['imageName']
        recommended[image_name] = str(img.get('imageTag', img.get('imageTar', 'latest')))

    return recommended

def parse_image_tag(image_string):
    """Parse image name and tag from Docker image string

    Args:
        image_string: e.g. "registry/image:tag"

    Returns:
        tuple: (image_name, tag)
    """
    if ':' in image_string:
        image_name, tag = image_string.rsplit(':', 1)
    else:
        image_name = image_string
        tag = 'latest'

    return image_name, tag

def compare_version_tags(current, recommended):
    """Compare version tags to determine if update needed

    Args:
        current: Current version tag
        recommended: Recommended version tag

    Returns:
        bool: True if update recommended
    """
    if current == recommended:
        return False

    try:
        def normalize(ver):
            ver = re.sub(r'^[vV]', '', ver)
            ver = re.sub(r'(-[A-Z]\d+)$', '', ver)
            parts = ver.split('.')
            while len(parts) < 3:
                parts.append('0')
            return '.'.join(parts[:3])

        current_norm = normalize(current)
        recommended_norm = normalize(recommended)

        return pkg_version.parse(recommended_norm) > pkg_version.parse(current_norm)
    except:
        return current != recommended

def compare_container_versions():
    """Compare running containers with recommended versions

    Returns:
        list: Container info with version comparison
    """
    recommended = fetch_recommended_versions()
    containers = []

    for container in client.containers.list(all=True):
        if container.name == 'supos-bedrock':
            continue

        image_tags = container.image.tags
        if not image_tags:
            continue

        current_image = image_tags[0]
        image_name, current_tag = parse_image_tag(current_image)

        recommended_tag = None
        container_base_name = container.name.lower()

        for rec_name, rec_tag in recommended.items():
            rec_image_name = rec_name.split('/')[-1].lower()
            image_short_name = image_name.split('/')[-1].lower()

            if container_base_name == rec_image_name or image_short_name == rec_image_name:
                recommended_tag = rec_tag
                break

        update_available = False
        if recommended_tag and current_tag != recommended_tag:
            update_available = compare_version_tags(current_tag, recommended_tag)

        containers.append({
            'id': container.id[:12],
            'name': container.name,
            'status': container.status,
            'current_version': current_tag,
            'recommended_version': recommended_tag,
            'update_available': update_available,
            'image': current_image
        })

    return containers

def update_container_version(container_name, recommended_tag):
    """Update container to recommended version

    Args:
        container_name: Name of container
        recommended_tag: Target version tag

    Returns:
        dict: Update result
    """
    try:
        container = client.containers.get(container_name)
        current_image = container.image.tags[0] if container.image.tags else None

        if not current_image:
            return {"success": False, "error": "No current image found"}

        image_name, current_tag = parse_image_tag(current_image)
        new_image = f"{image_name}:{recommended_tag}"

        env_file = os.path.join(WORKSPACE, '.env')
        compose_file = os.path.join(WORKSPACE, 'docker-compose-8c16g.yml')
        override_file = os.path.join(WORKSPACE, 'docker-compose.override.yml')

        override_content = f"""
services:
  {container_name}:
    image: {new_image}
"""

        with open(override_file, 'w') as f:
            f.write(override_content)

        try:
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
                return {
                    'success': False,
                    'error': f'Update failed: {result.stderr}',
                    'stdout': result.stdout
                }

            return {
                'success': True,
                'container': container_name,
                'old_version': current_tag,
                'new_version': recommended_tag,
                'message': f'Updated {container_name} from {current_tag} to {recommended_tag}'
            }

        finally:
            if os.path.exists(override_file):
                os.remove(override_file)

    except docker.errors.NotFound:
        return {"success": False, "error": f'Container {container_name} not found'}
    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }
