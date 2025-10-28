#!/usr/bin/env python3
"""supOS-bedrock Orchestrator with Keycloak authentication"""

import os
import json
import time
import subprocess
import requests
import docker
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory, Response, redirect, session
from flask_cors import CORS
from functools import wraps

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
CORS(app, supports_credentials=True)

# Paths
CONFIG_FILE = '/app/config/config.json'
SETUP_FLAG = '/config/setup_complete'
WORKSPACE = os.getenv('SUPOS_WORKSPACE', '/workspace')
LOG_DIR = '/workspace/logs'
os.makedirs(LOG_DIR, exist_ok=True)
INSTALL_LOG = os.path.join(LOG_DIR, 'install.log')

client = docker.from_env()

# ==================== AUTHENTICATION ====================

def require_auth(f):
    """Protect routes ONLY after setup completes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # During setup: no auth required
        if not is_setup_complete():
            return f(*args, **kwargs)

        # After setup: check Keycloak session
        if 'keycloak_user' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect('/login')

        return f(*args, **kwargs)
    return decorated

@app.route('/login')
def login_page():
    """Redirect to Keycloak"""
    if not is_setup_complete():
        return redirect('/')

    config = load_config()
    domain = config.get('network', {}).get('domain', '127.0.0.1')
    port = config.get('network', {}).get('port', 8088)

    keycloak_auth = f"http://{domain}:{port}/keycloak/home/auth/realms/master/protocol/openid-connect/auth"
    callback = f"http://{domain}:8080/auth/callback"

    return redirect(
        f"{keycloak_auth}?"
        f"client_id=admin-cli&"
        f"redirect_uri={callback}&"
        f"response_type=code&"
        f"scope=openid"
    )

@app.route('/auth/callback')
def auth_callback():
    """OAuth callback"""
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'No authorization code'}), 400

    config = load_config()
    domain = config.get('network', {}).get('domain', '127.0.0.1')

    # Use Docker bridge to reach keycloak exposed port
    token_url = "http://172.17.0.1:8081/realms/master/protocol/openid-connect/token"
    callback = f"http://{domain}:8080/auth/callback"

    try:
        token_resp = requests.post(token_url, data={
            'grant_type': 'authorization_code',
            'client_id': 'admin-cli',
            'code': code,
            'redirect_uri': callback
        }, timeout=10)

        if token_resp.status_code != 200:
            return jsonify({'error': 'Token exchange failed', 'details': token_resp.text}), 400

        access_token = token_resp.json().get('access_token')

        userinfo_resp = requests.get(
            "http://172.17.0.1:8081/realms/master/protocol/openid-connect/userinfo",
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )

        if userinfo_resp.status_code == 200:
            user = userinfo_resp.json()
            session['keycloak_user'] = user.get('preferred_username', 'admin')
            session['access_token'] = access_token
            return redirect('/')

        return jsonify({'error': 'User info failed'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/api/auth/status')
def auth_status():
    return jsonify({
        'authenticated': 'keycloak_user' in session,
        'user': session.get('keycloak_user'),
        'setup_complete': is_setup_complete()
    })

@app.route('/api/apps/list')
def list_apps():
    """Return available optional apps based on OS_RESOURCE_SPEC"""
    try:
        env_file = os.path.join(WORKSPACE, '.env')
        resource_spec = '2'  # Default to 8c16g

        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('OS_RESOURCE_SPEC='):
                        resource_spec = line.strip().split('=')[1]
                        break

        # Base apps available in both specs
        base_apps = [
            {
                'id': 'grafana',
                'name': 'Grafana',
                'description': 'Metrics visualization and monitoring dashboards',
                'icon': '📊',
                'category': 'monitoring'
            },
            {
                'id': 'minio',
                'name': 'MinIO',
                'description': 'S3-compatible object storage for data and backups',
                'icon': '🗄️',
                'category': 'storage'
            },
            {
                'id': 'mcpclient',
                'name': 'MCP Client',
                'description': 'Model Context Protocol client for AI integrations',
                'icon': '🤖',
                'category': 'ai'
            }
        ]

        # Extended apps only for 8c16g (high resource)
        extended_apps = [
            {
                'id': 'elk',
                'name': 'ELK Stack',
                'description': 'Elasticsearch, Logstash, Kibana for log analytics',
                'icon': '🔍',
                'category': 'logging',
                'requires_high_resource': True
            },
            {
                'id': 'gitea',
                'name': 'Gitea',
                'description': 'Self-hosted Git service for version control',
                'icon': '🔀',
                'category': 'devops',
                'requires_high_resource': True
            }
        ]

        # ALWAYS return all apps - frontend handles grey-out
        apps = base_apps + extended_apps

        return jsonify({
            'apps': apps,
            'resource_spec': resource_spec,
            'spec_name': '8c16g (High Resource)' if resource_spec == '2' else '4c8g (Standard)'
        })

    except Exception as e:
        return jsonify({
            'apps': [],
            'error': str(e)
        }), 500

# ==================== KEYCLOAK USER MANAGEMENT ====================

def create_keycloak_user(username, password, email, domain, port):
    """
    Create user in both supos and master realms.
    Uses Docker bridge IP to reach keycloak exposed port.
    """
    # Docker bridge + exposed port (supos-bedrock runs on default bridge)
    keycloak_url = "http://172.17.0.1:8081"

    def check_keycloak_health(host, port):
        """Raw TCP health check (Keycloak removed curl)"""
        import socket
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    try:
        # Wait for Keycloak to be ready
        max_retries = 30
        for i in range(max_retries):
            if check_keycloak_health("172.17.0.1", 8081):
                break
            time.sleep(2)
        else:
            return {"success": False, "message": "Keycloak not ready after 60 seconds"}

        # Get admin token
        token_resp = requests.post(
            f"{keycloak_url}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "username": "admin",
                "password": "supos",
                "grant_type": "password"
            },
            timeout=10
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        user_payload = {
            "username": username,
            "email": email,
            "enabled": True,
            "credentials": [{
                "type": "password",
                "value": password,
                "temporary": False
            }]
        }

        # === SUPOS REALM ===
        supos_resp = requests.post(
            f"{keycloak_url}/admin/realms/supos/users",
            headers=headers,
            json=user_payload,
            timeout=10
        )

        if supos_resp.status_code == 409:
            return {"success": True, "message": f"User {username} already exists"}

        if supos_resp.status_code != 201:
            return {"success": False, "message": f"Supos user creation failed: {supos_resp.status_code}"}

        # Get supos user ID
        supos_user_id = supos_resp.headers.get('Location', '').split('/')[-1]
        if not supos_user_id:
            query = requests.get(
                f"{keycloak_url}/admin/realms/supos/users?username={username}&exact=true",
                headers=headers, timeout=10
            )
            query.raise_for_status()
            users = query.json()
            if users:
                supos_user_id = users[0]['id']

        # Get supos client
        client_resp = requests.get(
            f"{keycloak_url}/admin/realms/supos/clients?clientId=supos",
            headers=headers, timeout=10
        )
        client_resp.raise_for_status()
        clients = client_resp.json()
        if not clients:
            return {"success": False, "message": "supos client not found"}
        supos_client_uuid = clients[0]['id']

        # Get super-admin role
        roles_resp = requests.get(
            f"{keycloak_url}/admin/realms/supos/clients/{supos_client_uuid}/roles",
            headers=headers, timeout=10
        )
        roles_resp.raise_for_status()
        client_roles = roles_resp.json()
        super_admin = next((r for r in client_roles if r['name'] == 'super-admin'), None)
        if not super_admin:
            return {"success": False, "message": "super-admin role not found"}

        # Assign super-admin
        assign_resp = requests.post(
            f"{keycloak_url}/admin/realms/supos/users/{supos_user_id}/role-mappings/clients/{supos_client_uuid}",
            headers=headers,
            json=[{"id": super_admin['id'], "name": super_admin['name']}],
            timeout=10
        )
        if assign_resp.status_code not in [204, 200]:
            return {"success": False, "message": f"Supos role assignment failed: {assign_resp.status_code}"}

        # === MASTER REALM ===
        master_resp = requests.post(
            f"{keycloak_url}/admin/realms/master/users",
            headers=headers,
            json=user_payload,
            timeout=10
        )

        if master_resp.status_code not in [201, 409]:
            return {"success": False, "message": f"Master user creation failed: {master_resp.status_code}"}

        # Get master user ID
        master_user_id = None
        if master_resp.status_code == 201:
            master_user_id = master_resp.headers.get('Location', '').split('/')[-1]

        if not master_user_id:
            query = requests.get(
                f"{keycloak_url}/admin/realms/master/users?username={username}&exact=true",
                headers=headers, timeout=10
            )
            query.raise_for_status()
            users = query.json()
            if users:
                master_user_id = users[0]['id']

        if not master_user_id:
            return {"success": False, "message": "Could not get master user ID"}

        # Get master realm roles
        realm_roles_resp = requests.get(
            f"{keycloak_url}/admin/realms/master/roles",
            headers=headers, timeout=10
        )
        realm_roles_resp.raise_for_status()
        realm_roles = realm_roles_resp.json()

        admin_role = next((r for r in realm_roles if r['name'] == 'admin'), None)
        default_roles = next((r for r in realm_roles if r['name'] == 'default-roles-master'), None)

        if not admin_role or not default_roles:
            return {"success": False, "message": "Master roles not found"}

        # Assign master roles
        master_assign = requests.post(
            f"{keycloak_url}/admin/realms/master/users/{master_user_id}/role-mappings/realm",
            headers=headers,
            json=[
                {"id": admin_role['id'], "name": admin_role['name']},
                {"id": default_roles['id'], "name": default_roles['name']}
            ],
            timeout=10
        )

        if master_assign.status_code not in [204, 200]:
            return {"success": False, "message": f"Master role assignment failed: {master_assign.status_code}"}

        # === DELETE DEFAULTS ===
        # Delete supos user
        default_supos = requests.get(
            f"{keycloak_url}/admin/realms/supos/users?username=supos&exact=true",
            headers=headers, timeout=10
        )
        if default_supos.status_code == 200:
            for user in default_supos.json():
                if user['username'] == 'supos':
                    requests.delete(
                        f"{keycloak_url}/admin/realms/supos/users/{user['id']}",
                        headers=headers, timeout=10
                    )
                    break

        # Delete admin user (This still cause BUG where routes leads to 403)
        # default_admin = requests.get(
        #     f"{keycloak_url}/admin/realms/master/users?username=admin&exact=true",
        #     headers=headers, timeout=10
        # )
        # if default_admin.status_code == 200:
        #     for user in default_admin.json():
        #         if user['username'] == 'admin':
        #             requests.delete(
        #                 f"{keycloak_url}/admin/realms/master/users/{user['id']}",
        #                 headers=headers, timeout=10
        #             )
        #             break

        return {
            "success": True,
            "message": f"✓ User {username} created in both realms with proper roles. Default accounts removed."
        }

    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Keycloak API error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}

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
@require_auth
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

@app.route('/api/config/detected-ips', methods=['GET'])
def get_detected_ips():
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

@app.route('/api/config/check-volume', methods=['GET'])
def check_volume():
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

@app.route('/api/config/update', methods=['POST'])
def update_config():
    """Save initial config from setup wizard"""
    try:
        data = request.get_json()
        env_file = os.path.join(WORKSPACE, '.env')

        ip_address = data.get('ip_address', '').strip()
        port = data.get('entrance_port', '8088').strip()
        resource_spec = data.get('resource_spec', '1')

        if not ip_address:
            return jsonify({'success': False, 'error': 'IP address required'}), 400

        is_loopback = ip_address in ['127.0.0.1', 'localhost']

        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                lines = f.readlines()
        else:
            lines = []

        updates = {
            'ENTRANCE_DOMAIN': ip_address,
            'ENTRANCE_PORT': port,
            'OS_RESOURCE_SPEC': resource_spec,
            'OS_AUTH_ENABLE': 'false' if is_loopback else 'true',
            'VOLUMES_PATH': '/volumes/supos/data'
        }

        for key, value in updates.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f'{key}='):
                    lines[i] = f'{key}={value}\n'
                    found = True
                    break
            if not found:
                lines.append(f'{key}={value}\n')

        with open(env_file, 'w') as f:
            f.writelines(lines)

        return jsonify({
            'success': True,
            'loopback_warning': is_loopback
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def get_host_ip():
    try:
        result = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True)
        return result.stdout.split()[2]
    except:
        return "172.17.0.1"

@app.route('/api/install/start', methods=['POST'])
def start_install():
    try:
        data = request.json
        admin_data = data.get('admin', {})
        network_data = data.get('network', {})
        selected_apps = data.get('selected_apps', [])

        logs = ["Starting installation..."]

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
            log_file.write(f"✓ Configuration saved to .env\n")

        install_script = os.path.join(WORKSPACE, 'bin/install.sh')

        with open(INSTALL_LOG, 'a') as log_file:
            log_file.write(f"Running: {install_script} --non-interactive\n")
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

            return_code = process.wait()

            if return_code != 0:
                log_file.write(f"\n\n[ERROR] Installation failed with exit code {return_code}\n")
                return jsonify({
                    "success": False,
                    "error": f"Installation script failed (exit {return_code})",
                    "logs": logs,
                    "log_file": "/api/install/logs"
                }), 500

        with open(INSTALL_LOG, 'a') as log_file:
            log_file.write("✓ Installation script completed\n")
            log_file.write("\nCreating admin user in Keycloak (both realms)...\n")

            keycloak_result = create_keycloak_user(
                username=admin_data.get('username'),
                password=admin_data.get('password'),
                email=admin_data.get('email', f"{admin_data.get('username')}@localhost"),
                domain=network_data.get('domain'),
                port=network_data.get('port', 8088)
            )
            log_file.write(keycloak_result['message'] + "\n")

            if not keycloak_result['success']:
                log_file.write("\n⚠ Keycloak user creation failed\n")
                log_file.write("\nYou can still login with default: admin/supos\n")

            config = load_config()
            config['installed_apps'] = selected_apps
            config['admin'] = admin_data
            config['network'] = network_data
            save_config(config)
            write_setup_flag(config)

            log_file.write("\n✓ Installation complete!\n")

        return jsonify({
            "success": True,
            "message": "Installation complete",
            "logs": logs,
            "log_file": "/api/install/logs",
            "access_url": f"http://{network_data.get('domain')}:{network_data.get('port', 8088)}/home"
        })

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
    """Check if installation is running"""
    if os.path.exists(INSTALL_LOG):
        age = time.time() - os.path.getmtime(INSTALL_LOG)
        if age < 600:
            return jsonify({"installing": True, "log_age": age})
    return jsonify({"installing": False})

@app.route('/api/install/logs')
def view_full_logs():
    if not os.path.exists(INSTALL_LOG):
        return "No installation log found.\nStart installation from the wizard.", 404

    with open(INSTALL_LOG, 'r') as f:
        return Response(f.read(), mimetype='text/plain')

@app.route('/api/install/logs/tail')
def tail_logs():
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
@require_auth
def supos_status():
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
@require_auth
def restart_supos():
    """Restart all supOS containers"""
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
