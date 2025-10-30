"""Installation management and log handling"""

import os
import re
import subprocess
import threading
from datetime import datetime

from config import WORKSPACE, save_config, write_setup_flag, update_env_file, read_env_file
from auth import create_keycloak_user, configure_supos_client_callback

LOG_DIR = '/workspace/logs'
os.makedirs(LOG_DIR, exist_ok=True)
INSTALL_LOG = os.path.join(LOG_DIR, 'install.log')

# Global state for installation tracking
installation_process = None
installation_data = {}

def sanitize_log_line(line):
    """Remove sensitive data from log lines

    Args:
        line: Log line to sanitize

    Returns:
        str: Sanitized line
    """
    line = re.sub(r'(PASSWORD|TOKEN|SECRET|KEY)=\S+', r'\1=***REDACTED***', line, flags=re.IGNORECASE)
    line = re.sub(r'--password[\s=]\S+', r'--password=***REDACTED***', line, flags=re.IGNORECASE)
    line = re.sub(r'-p[\s=]\S+', r'-p=***REDACTED***', line)
    line = re.sub(r'(Admin|Username|User):\s*\S+', r'\1: ***REDACTED***', line, flags=re.IGNORECASE)

    if 'Default user name:' in line:
        return ''
    if line.strip().startswith('password:') and line.strip() != 'password: ***REDACTED***':
        return ''

    if 'User' in line and 'created in both realms' in line:
        return '✓ Custom admin user created successfully\n'

    return line

def get_host_ip():
    """Get host IP for orchestrator communication

    Returns:
        str: Host IP address
    """
    try:
        result = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True)
        return result.stdout.split()[2]
    except:
        return "172.17.0.1"

def run_installation_async(admin_data, network_data, selected_apps):
    """Run installation in background thread

    Args:
        admin_data: dict with username, password, email
        network_data: dict with domain, port
        selected_apps: list of app names to install
    """
    global installation_data

    try:
        env_vars = read_env_file()

        updates = {
            'KEYCLOAK_ADMIN_USERNAME': admin_data.get('username', 'admin'),
            'KEYCLOAK_ADMIN_PASSWORD': admin_data.get('password', 'admin'),
            'ENTRANCE_DOMAIN': network_data.get('domain', env_vars.get('ENTRANCE_DOMAIN')),
            'ENTRANCE_PORT': str(network_data.get('port', env_vars.get('ENTRANCE_PORT', '8088'))),
            'SELECTED_PROFILES': ','.join(selected_apps),
            'ORCHESTRATOR_HOST': get_host_ip()
        }

        env_vars.update(updates)

        env_file = os.path.join(WORKSPACE, '.env')
        with open(env_file, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')

        with open(INSTALL_LOG, 'w') as log_file:
            log_file.write(f"✓ Configuration saved to .env\n")

        install_script = os.path.join(WORKSPACE, 'bin/install.sh')

        with open(INSTALL_LOG, 'a') as log_file:
            log_file.write(f"Running: {install_script} --non-interactive\n")
            log_file.write(f"\n=== Installation started at {datetime.now()} ===\n")
            log_file.write(f"Admin: ***REDACTED***\n")
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

            installation_data['process'] = process
            installation_data['status'] = 'running'

            return_code = process.wait()

            if return_code != 0:
                log_file.write(f"\n\n[ERROR] Installation failed with exit code {return_code}\n")
                installation_data['status'] = 'failed'
                installation_data['error'] = f"Installation script failed (exit {return_code})"
                return

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

            log_file.write("\nConfiguring supos client for orchestrator...\n")
            supos_result = configure_supos_client_callback(
                domain=network_data.get('domain'),
                port=network_data.get('port', 8088)
            )
            log_file.write(supos_result['message'] + "\n")

            if not keycloak_result['success']:
                log_file.write("\n⚠ Keycloak user creation failed\n")

            from config import load_config
            config = load_config()
            config['installed_apps'] = selected_apps
            config['admin'] = {'username': admin_data.get('username'), 'email': admin_data.get('email')}
            config['network'] = network_data
            save_config(config)
            write_setup_flag(config)

            log_file.write("\n✓ Installation complete!\n")

        installation_data['status'] = 'completed'
        installation_data['access_url'] = f"http://{network_data.get('domain')}:{network_data.get('port', 8088)}/home"

    except Exception as e:
        import traceback
        with open(INSTALL_LOG, 'a') as f:
            f.write(f"\n\n[EXCEPTION]\n{traceback.format_exc()}\n")
        installation_data['status'] = 'failed'
        installation_data['error'] = str(e)

def start_installation(admin_data, network_data, selected_apps):
    """Start installation in background thread

    Args:
        admin_data: dict with username, password, email
        network_data: dict with domain, port
        selected_apps: list of app names

    Returns:
        dict: {"success": bool, "message": str}
    """
    global installation_process, installation_data

    installation_data = {
        'status': 'starting',
        'started_at': datetime.now().isoformat()
    }

    thread = threading.Thread(
        target=run_installation_async,
        args=(admin_data, network_data, selected_apps),
        daemon=True
    )
    thread.start()
    installation_process = thread

    return {
        "success": True,
        "message": "Installation started in background"
    }

def get_installation_status():
    """Get current installation status

    Returns:
        dict: status information
    """
    global installation_data
    return installation_data

def read_install_logs(from_line=0):
    """Read installation logs from specific line

    Args:
        from_line: Starting line number

    Returns:
        dict: log data
    """
    if not os.path.exists(INSTALL_LOG):
        return {
            "lines": [],
            "current_line": 0,
            "completed": False,
            "failed": False
        }

    with open(INSTALL_LOG, 'r') as f:
        all_lines = f.readlines()

    new_lines = all_lines[from_line:]
    sanitized = [sanitize_log_line(line.rstrip()) for line in new_lines]

    status = installation_data.get('status', 'unknown')

    return {
        "lines": sanitized,
        "current_line": len(all_lines),
        "completed": status == 'completed',
        "failed": status == 'failed',
        "status": status
    }
