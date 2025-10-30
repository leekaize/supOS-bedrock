"""Routes package - register all blueprints"""

from .setup import setup_bp
from .install import install_bp
from .auth_routes import auth_routes_bp
from .container import container_bp
from .version import version_bp
from .backup import backup_bp

__all__ = [
    'setup_bp',
    'install_bp',
    'auth_routes_bp',
    'container_bp',
    'version_bp',
    'backup_bp'
]
