"""Keycloak authentication and session management - EXACT original implementation"""

import time
import socket
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import session, redirect, jsonify, request

from config import is_setup_complete

def validate_token_with_retry(max_retries=3):
    """Validate Keycloak access token with retry logic"""
    if 'access_token' not in session:
        return False

    for attempt in range(max_retries):
        try:
            response = requests.get(
                'http://172.17.0.1:8081/realms/supos/protocol/openid-connect/userinfo',
                headers={'Authorization': f"Bearer {session['access_token']}"},
                timeout=5
            )

            if response.status_code == 200:
                return True

            if response.status_code == 401 and attempt < max_retries - 1:
                if refresh_access_token():
                    continue
                else:
                    return False

        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue

    return False

def refresh_access_token():
    """Attempt to refresh access token using refresh token"""
    if 'refresh_token' not in session:
        return False

    try:
        response = requests.post(
            'http://172.17.0.1:8081/realms/supos/protocol/openid-connect/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': session['refresh_token'],
                'client_id': 'supos',
                'client_secret': 'VaOS2makbDhJJsLlYPt4Wl87bo9VzXiO'
            },
            timeout=10
        )

        if response.status_code == 200:
            token_data = response.json()
            session['access_token'] = token_data.get('access_token')
            session['refresh_token'] = token_data.get('refresh_token')
            session['token_expires_at'] = (
                datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 300))
            ).isoformat()
            session.modified = True
            return True

    except Exception:
        pass

    return False

def require_auth(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_setup_complete():
            return f(*args, **kwargs)

        if validate_token_with_retry():
            return f(*args, **kwargs)

        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Authentication required',
                'message': 'Please log in again',
                'redirect': '/login'
            }), 401

        return redirect('/login')

    return decorated

def create_keycloak_user(username, password, email, domain, port):
    """Create user in both supos and master realms with proper roles - EXACT original"""
    keycloak_url = "http://172.17.0.1:8081"

    def check_keycloak_health(host, port):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    try:
        # Wait for Keycloak to be ready
        for i in range(30):
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
            "emailVerified": True,
            "credentials": [{
                "type": "password",
                "value": password,
                "temporary": False
            }]
        }

        # Create user in supos realm
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

        # Get supos client UUID
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

        # Assign super-admin role in supos realm
        assign_resp = requests.post(
            f"{keycloak_url}/admin/realms/supos/users/{supos_user_id}/role-mappings/clients/{supos_client_uuid}",
            headers=headers,
            json=[{"id": super_admin['id'], "name": super_admin['name']}],
            timeout=10
        )
        if assign_resp.status_code not in [204, 200]:
            return {"success": False, "message": f"Supos role assignment failed: {assign_resp.status_code}"}

        # Create user in master realm
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

        # Assign admin + default-roles-master in master realm
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

        return {
            "success": True,
            "message": f"✓ User {username} created in both realms with proper roles"
        }

    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Keycloak API error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}

def configure_supos_client_callback(domain, port=8088):
    """Configure supos client in supos realm with orchestrator callback - EXACT original"""
    keycloak_url = "http://172.17.0.1:8081"
    orchestrator_callback = f"http://{domain}:8080/auth/callback"
    supos_callback = f"http://{domain}:{port}/inter-api/supos/auth/token"

    try:
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

        if token_resp.status_code != 200:
            return {"success": False, "message": f"Token error: {token_resp.text}"}

        token = token_resp.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Find supos client in supos realm
        clients_resp = requests.get(
            f"{keycloak_url}/admin/realms/supos/clients?clientId=supos",
            headers=headers,
            timeout=10
        )

        if clients_resp.status_code != 200:
            return {"success": False, "message": f"Client query failed: {clients_resp.text}"}

        clients = clients_resp.json()
        if not clients:
            return {"success": False, "message": "supos client not found in supos realm"}

        client_uuid = clients[0]["id"]

        # Get current client config
        config_resp = requests.get(
            f"{keycloak_url}/admin/realms/supos/clients/{client_uuid}",
            headers=headers,
            timeout=10
        )

        if config_resp.status_code != 200:
            return {"success": False, "message": f"Config fetch failed: {config_resp.text}"}

        client_config = config_resp.json()

        # Update redirect URIs
        redirect_uris = client_config.get("redirectUris", [])
        new_uris = [
            orchestrator_callback,
            f"http://{domain}:8080/*",
            supos_callback,
            f"http://{domain}:{port}/*"
        ]

        for uri in new_uris:
            if uri not in redirect_uris:
                redirect_uris.append(uri)

        client_config["redirectUris"] = redirect_uris

        # Update client
        update_resp = requests.put(
            f"{keycloak_url}/admin/realms/supos/clients/{client_uuid}",
            headers=headers,
            json=client_config,
            timeout=10
        )

        if update_resp.status_code not in [200, 204]:
            return {"success": False, "message": f"Update failed: {update_resp.status_code} - {update_resp.text}"}

        return {"success": True, "message": f"✓ supos client configured: {orchestrator_callback}, {supos_callback}"}

    except Exception as e:
        import traceback
        return {"success": False, "message": f"Exception: {traceback.format_exc()}"}
