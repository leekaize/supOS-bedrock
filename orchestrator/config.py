"""Configuration management for supOS-bedrock orchestrator"""

import os
import json
from datetime import datetime

CONFIG_FILE = '/app/config/config.json'
SETUP_FLAG = '/config/setup_complete'
WORKSPACE = os.getenv('SUPOS_WORKSPACE', '/workspace')

def load_config():
    """Load configuration from JSON file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    return {
        "setup_complete": False,
        "admin": {},
        "network": {
            "domain": os.getenv("ENTRANCE_DOMAIN", "127.0.0.1"),
            "port": int(os.getenv("ENTRANCE_PORT", 8088))
        },
        "system": {"volumes_path": os.getenv("VOLUMES_PATH", "/volumes/supos/data")},
        "selected_apps": [],
        "installed_apps": []
    }

def save_config(config):
    """Save configuration to JSON file"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def is_setup_complete():
    """Check if initial setup is complete"""
    return os.path.exists(SETUP_FLAG)

def write_setup_flag(config):
    """Write setup completion flag"""
    os.makedirs(os.path.dirname(SETUP_FLAG), exist_ok=True)
    with open(SETUP_FLAG, 'w') as f:
        json.dump({
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "admin_username": config.get("admin", {}).get("username", "admin"),
            "installed_apps": config.get("installed_apps", [])
        }, f, indent=2)

def update_env_file(updates):
    """Update .env file with new values

    Args:
        updates: dict of key-value pairs to update

    Returns:
        bool: True if successful
    """
    env_file = os.path.join(WORKSPACE, '.env')

    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()
    else:
        lines = []

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

    return True

def read_env_file():
    """Read .env file and return as dict"""
    env_file = os.path.join(WORKSPACE, '.env')
    env_vars = {}

    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_vars[key] = value

    return env_vars
