"""OAuth authentication routes"""

import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, redirect, session

from config import load_config, is_setup_complete
from auth import validate_token_with_retry

auth_routes_bp = Blueprint('auth_routes', __name__)

@auth_routes_bp.route('/login')
def login_page():
    """Redirect to Keycloak login"""
    if not is_setup_complete():
        return redirect('/')

    config = load_config()
    domain = config.get('network', {}).get('domain', '127.0.0.1')
    port = config.get('network', {}).get('port', 8088)

    keycloak_auth = f"http://{domain}:{port}/keycloak/home/auth/realms/supos/protocol/openid-connect/auth"
    callback = f"http://{domain}:8080/auth/callback"

    return redirect(
        f"{keycloak_auth}?"
        f"client_id=supos&"
        f"redirect_uri={callback}&"
        f"response_type=code&"
        f"scope=openid"
    )

@auth_routes_bp.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback from Keycloak"""
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'No authorization code'}), 400

    config = load_config()
    domain = config.get('network', {}).get('domain', '127.0.0.1')
    token_url = "http://172.17.0.1:8081/realms/supos/protocol/openid-connect/token"
    callback = f"http://{domain}:8080/auth/callback"

    try:
        token_resp = requests.post(token_url, data={
            'grant_type': 'authorization_code',
            'client_id': 'supos',
            'client_secret': 'VaOS2makbDhJJsLlYPt4Wl87bo9VzXiO',
            'code': code,
            'redirect_uri': callback
        }, timeout=10)

        if token_resp.status_code != 200:
            return jsonify({'error': 'Token exchange failed', 'details': token_resp.text}), 400

        token_data = token_resp.json()

        userinfo_resp = requests.get(
            "http://172.17.0.1:8081/realms/supos/protocol/openid-connect/userinfo",
            headers={'Authorization': f"Bearer {token_data['access_token']}"},
            timeout=10
        )

        if userinfo_resp.status_code == 200:
            user = userinfo_resp.json()

            session.permanent = True
            session['keycloak_user'] = user.get('preferred_username', 'admin')
            session['access_token'] = token_data.get('access_token')
            session['refresh_token'] = token_data.get('refresh_token')
            session['token_expires_at'] = (
                datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 300))
            ).isoformat()
            session['session_created_at'] = datetime.utcnow().isoformat()
            session.modified = True

            return redirect('/')

        return jsonify({'error': 'User info failed'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_routes_bp.route('/logout')
def logout():
    """Clear session and logout"""
    session.clear()
    return redirect('/')

@auth_routes_bp.route('/api/auth/status')
def auth_status():
    """Get authentication status"""
    is_authenticated = validate_token_with_retry()

    return jsonify({
        'authenticated': is_authenticated,
        'user': session.get('keycloak_user'),
        'setup_complete': is_setup_complete(),
        'token_expires_at': session.get('token_expires_at')
    })
