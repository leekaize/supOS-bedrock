#!/usr/bin/env python3
"""supOS-bedrock Orchestrator - Production with Keycloak API + Log Streaming"""

import os
import json
import time
import subprocess
import requests
import docker
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Paths
CONFIG_FILE = '/app/config/config.json'
SETUP_FLAG = '/config/setup_complete'
WORKSPACE = os.getenv('SUPOS_WORKSPACE', '/workspace')
LOG_DIR = '/workspace/logs'
os.makedirs(LOG_DIR, exist_ok=True)
INSTALL_LOG = os.path.join(LOG_DIR, 'install.log')

client = docker.from_env()

# ========== Detect IPs ==========
@app.route('/api/config/detected-ips', methods=['GET'])
def get_detected_ips():
    """
    Returns all IPs from HOST_IPS env var.
    User runs: docker run -e HOST_IPS=$(hostname -I) ...
    Returns space-separated IPs as array.
    """
    try:
        # Read from environment variable (space-separated)
        host_ips_raw = os.environ.get('HOST_IPS', '').strip()

        # Parse space-separated IPs
        if host_ips_raw:
            detected_ips = host_ips_raw.split()
        else:
            detected_ips = []

        # Always include localhost as option
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

# ========== Validate Volume Mount ==========
@app.route('/api/config/check-volume', methods=['GET'])
def check_volume():
    """Verify /volumes/supos/data mounted and writable"""
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

# ==================== KEYCLOAK API ====================

def create_keycloak_user(username, password, email, domain, port):
    """Create user in supos realm with super-admin CLIENT role and delete default user."""
    keycloak_url = f"http://{domain}:{port}/keycloak/home"

    try:
        # Step 1: Get master admin token
        token_response = requests.post(
            f"{keycloak_url}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "username": "admin",
                "password": "supos",
                "grant_type": "password"
            },
            timeout=10
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Step 2: Create user in supos realm
        user_response = requests.post(
            f"{keycloak_url}/admin/realms/supos/users",
            headers=headers,
            json={
                "username": username,
                "email": email,
                "enabled": True,
                "credentials": [{
                    "type": "password",
                    "value": password,
                    "temporary": False
                }]
            },
            timeout=10
        )

        if user_response.status_code == 409:
            return {"success": True, "message": f"User {username} already exists"}

        if user_response.status_code != 201:
            return {"success": False, "message": f"User creation failed: HTTP {user_response.status_code}"}

        # Step 3: Get created user's ID
        user_id = user_response.headers.get('Location', '').split('/')[-1]
        if not user_id:
            query_response = requests.get(
                f"{keycloak_url}/admin/realms/supos/users?username={username}&exact=true",
                headers=headers,
                timeout=10
            )
            query_response.raise_for_status()
            users = query_response.json()
            if users:
                user_id = users[0]['id']

        # Step 4: Get supos client UUID (not clientId)
        client_response = requests.get(
            f"{keycloak_url}/admin/realms/supos/clients?clientId=supos",
            headers=headers,
            timeout=10
        )
        client_response.raise_for_status()
        clients = client_response.json()

        if not clients:
            return {"success": False, "message": "supos client not found"}

        supos_client_uuid = clients[0]['id']

        # Step 5: Get super-admin role from supos CLIENT
        client_roles_response = requests.get(
            f"{keycloak_url}/admin/realms/supos/clients/{supos_client_uuid}/roles",
            headers=headers,
            timeout=10
        )
        client_roles_response.raise_for_status()
        client_roles = client_roles_response.json()

        super_admin_role = next((r for r in client_roles if r['name'] == 'super-admin'), None)
        if not super_admin_role:
            return {"success": False, "message": f"super-admin role not found in supos client. Available: {[r['name'] for r in client_roles]}"}

        # Step 6: Assign CLIENT role to user
        role_assign_response = requests.post(
            f"{keycloak_url}/admin/realms/supos/users/{user_id}/role-mappings/clients/{supos_client_uuid}",
            headers=headers,
            json=[{
                "id": super_admin_role['id'],
                "name": super_admin_role['name']
            }],
            timeout=10
        )

        if role_assign_response.status_code not in [204, 200]:
            return {"success": False, "message": f"Role assignment failed: HTTP {role_assign_response.status_code}"}

        # Step 7: Delete default 'supos' user
        default_user_response = requests.get(
            f"{keycloak_url}/admin/realms/supos/users?username=supos&exact=true",
            headers=headers,
            timeout=10
        )

        if default_user_response.status_code == 200:
            default_users = default_user_response.json()
            for default_user in default_users:
                if default_user['username'] == 'supos':
                    delete_response = requests.delete(
                        f"{keycloak_url}/admin/realms/supos/users/{default_user['id']}",
                        headers=headers,
                        timeout=10
                    )
                    if delete_response.status_code in [204, 200]:
                        break

        return {
            "success": True,
            "message": f"User {username} created with super-admin role. Default user removed."
        }

    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Keycloak API error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}

# ==================== CONFIG MANAGEMENT ====================

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "setup_complete": False,
        "admin": {},
        "network": {"domain": os.getenv("ENTRANCE_DOMAIN", "127.0.0.1"), "port": int(os.getenv("ENTRANCE_PORT", 8088))},
        "system": {"volumes_path": os.getenv("VOLUMES_PATH", "/volumes/supos/data")},
        "selected_apps": [],
        "installed_apps": []
    }

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def is_setup_complete():
    return os.path.exists(SETUP_FLAG)

def write_setup_flag(config):
    os.makedirs(os.path.dirname(SETUP_FLAG), exist_ok=True)
    with open(SETUP_FLAG, 'w') as f:
        json.dump({
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "admin_username": config.get("admin", {}).get("username", "admin"),
            "installed_apps": config.get("installed_apps", [])
        }, f, indent=2)

# ==================== ROUTES ====================

@app.route('/')
def index():
    if is_setup_complete():
        return jsonify({"message": "Setup complete", "redirect": "/api/supos/status"}), 200
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def catch_all(path):
    if os.path.exists(os.path.join('static', path)):
        return send_from_directory('static', path)
    return send_from_directory('static', 'index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "setup_complete": is_setup_complete()})

@app.route('/api/setup/status')
def setup_status():
    config = load_config()
    return jsonify({
        "setup_complete": is_setup_complete(),
        "config": config
    })

@app.route('/api/setup/validate', methods=['POST'])
def validate_setup():
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

        return jsonify({"valid": len(issues) == 0, "issues": issues, "warnings": warnings})
    except Exception as e:
        return jsonify({"valid": False, "issues": [str(e)], "warnings": []}), 500

@app.route('/api/config/volumes-path')
def get_volumes_path():
    try:
        path = os.getenv("VOLUMES_PATH", "/volumes/supos/data")
        return jsonify({"path": path, "mounted": os.path.exists(path)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== Update Config ==========
@app.route('/api/config/update', methods=['POST'])
def update_config():
    """
    Writes .env file for FIRST TIME.
    Called by setup wizard after user confirms settings.
    """
    try:
        data = request.get_json()
        env_file = os.path.join(WORKSPACE, '.env')

        # Extract inputs
        ip_address = data.get('ip_address', '').strip()
        port = data.get('entrance_port', '8088').strip()
        resource_spec = data.get('resource_spec', '1')

        if not ip_address:
            return jsonify({'success': False, 'error': 'IP address required'}), 400

        # Loopback check
        is_loopback = ip_address in ['127.0.0.1', 'localhost']

        # Read template .env or create from scratch
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                lines = f.readlines()
        else:
            # No template, create basic structure
            lines = []

        # Update/add required fields
        updates = {
            'ENTRANCE_DOMAIN': ip_address,
            'ENTRANCE_PORT': port,
            'OS_RESOURCE_SPEC': resource_spec,
            'OS_AUTH_ENABLE': 'false' if is_loopback else 'true',
            'VOLUMES_PATH': '/volumes/supos/data'
        }

        # Update existing or append new
        for key, value in updates.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f'{key}='):
                    lines[i] = f'{key}={value}\n'
                    found = True
                    break
            if not found:
                lines.append(f'{key}={value}\n')

        # Write .env
        with open(env_file, 'w') as f:
            f.writelines(lines)

        return jsonify({
            'success': True,
            'loopback_warning': is_loopback
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Get host IP that spawned containers can reach
def get_host_ip():
    """Get Docker bridge IP for inter-container communication."""
    try:
        result = subprocess.run(
            ['ip', 'route', 'show', 'default'],
            capture_output=True,
            text=True
        )
        # Extract default gateway
        default_gw = result.stdout.split()[2]
        return default_gw
    except:
        return "172.17.0.1"  # Docker bridge default

@app.route('/api/install/start', methods=['POST'])
def start_install():
    """Main installation endpoint with log streaming + Keycloak user creation."""
    try:
        data = request.json
        admin_data = data.get('admin', {})
        network_data = data.get('network', {})
        selected_apps = data.get('selected_apps', [])

        logs = ["Starting installation..."]

        # Update .env file
        env_file = os.path.join(WORKSPACE, '.env')
        with open(env_file, 'r') as f:
            env_vars = dict(line.strip().split('=', 1) for line in f if '=' in line and not line.startswith('#'))

        updates = {
            'KEYCLOAK_ADMIN_USERNAME': admin_data.get('username', 'admin'),
            'KEYCLOAK_ADMIN_PASSWORD': admin_data.get('password', 'admin'),
            'ENTRANCE_DOMAIN': network_data.get('domain', env_vars.get('ENTRANCE_DOMAIN')),
            'ENTRANCE_PORT': str(network_data.get('port', env_vars.get('ENTRANCE_PORT', '8088'))),
            'SELECTED_PROFILES': ','.join(selected_apps),
            'ORCHESTRATOR_HOST': get_host_ip()
        }

        env_vars.update(updates)

        with open(env_file, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')
        with open(INSTALL_LOG, 'w') as log_file:
            log_file.write(f"✓ Configuration saved to .env \n")

        # Run installation with log streaming
        install_script = os.path.join(WORKSPACE, 'bin/install.sh')

        with open(INSTALL_LOG, 'a') as log_file:
            log_file.write(f"Running: {install_script} --non-interactive")

            log_file.write(f"\n=== Installation started at {datetime.now()} ===\n")
            log_file.write(f"Admin: {admin_data.get('username')}\n")
            log_file.write(f"Domain: {network_data.get('domain')}\n")
            log_file.write(f"Apps: {', '.join(selected_apps) if selected_apps else 'none'}\n")
            log_file.write("="*60 + "\n\n")
            log_file.flush()

            process = subprocess.Popen(
                ['/bin/bash', install_script, '--non-interactive'],
                cwd=WORKSPACE,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ.copy()
            )

            # Wait for completion
            return_code = process.wait()

            if return_code != 0:
                with open(INSTALL_LOG, 'a') as f:
                    f.write(f"\n\n[ERROR] Installation failed with exit code {return_code}\n")
                return jsonify({
                    "success": False,
                    "error": f"Installation script failed (exit {return_code})",
                    "logs": logs,
                    "log_file": "/api/install/logs"
                }), 500

        with open(INSTALL_LOG, 'a') as log_file:
            log_file.write("✓ Installation script completed")

            # Wait for Keycloak and create admin user

            log_file.write("\nCreating admin user in Keycloak supos realm...")
            keycloak_result = create_keycloak_user(
                username=admin_data.get('username'),
                password=admin_data.get('password'),
                email=admin_data.get('email', f"{admin_data.get('username')}@localhost"),
                domain=network_data.get('domain'),
                port=network_data.get('port', 8088)
            )
            log_file.write(keycloak_result['message'])

            if not keycloak_result['success']:
                log_file.write("\n⚠ Keycloak user creation failed, but installation complete")
                log_file.write("\nYou can still login with default: supos/supos")

            # Save configuration
            config = load_config()
            config['installed_apps'] = selected_apps
            config['admin'] = admin_data
            config['network'] = network_data
            save_config(config)
            write_setup_flag(config)

            log_file.write("\n✓ Installation complete!")

            return jsonify({
                "success": True,
                "message": "Installation complete",
                "logs": logs,
                "log_file": "/api/install/logs",
                "access_url": f"http://{network_data.get('domain')}:{network_data.get('port', 8088)}/home"
            })

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Installation timeout (10 min)",
            "logs": logs,
            "log_file": "/api/install/logs"
        }), 500
    except Exception as e:
        import traceback
        with open(INSTALL_LOG, 'a') as f:
            f.write(f"\n\n[EXCEPTION]\n{traceback.format_exc()}\n")
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
            "logs": logs,
            "log_file": "/api/install/logs"
        }), 500

@app.route('/api/install/status')
def install_status():
    """Check if installation is running."""
    # Simple check: if install.log exists and is recent
    if os.path.exists(INSTALL_LOG):
        age = time.time() - os.path.getmtime(INSTALL_LOG)
        if age < 600:  # Modified in last 10 minutes
            return jsonify({"installing": True, "log_age": age})
    return jsonify({"installing": False})

@app.route('/api/install/logs')
def view_full_logs():
    """Stream complete installation log as plain text."""
    if not os.path.exists(INSTALL_LOG):
        return "No installation log found.\nStart installation from the wizard.", 404

    with open(INSTALL_LOG, 'r') as f:
        return Response(f.read(), mimetype='text/plain')

@app.route('/api/install/logs/tail')
def tail_logs():
    """Get last 100 lines for polling during installation."""
    if not os.path.exists(INSTALL_LOG):
        return jsonify({"logs": "", "exists": False}), 200

    try:
        with open(INSTALL_LOG, 'r') as f:
            lines = f.readlines()
            tail = ''.join(lines[-100:])
            return jsonify({"logs": tail, "exists": True, "total_lines": len(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/supos/status')
def supos_status():
    """Get supOS container status."""
    try:
        containers = client.containers.list(all=True, filters={"name": "supos"})
        status_list = []

        for container in containers:
            status_list.append({
                "name": container.name,
                "status": container.status,
                "id": container.short_id
            })

        return jsonify({
            "containers": status_list,
            "count": len(status_list)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/supos/restart', methods=['POST'])
def restart_supos():
    """Restart all supOS containers."""
    try:
        subprocess.run(
            ['docker', 'compose', 'restart'],
            cwd=WORKSPACE,
            check=True,
            capture_output=True
        )
        return jsonify({"success": True, "message": "Services restarted"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
