from flask import Blueprint
from .song import song_bp
from .billing import billing_bp

routes_bp = Blueprint('api/v1', __name__)

routes_bp.register_blueprint(song_bp)
routes_bp.register_blueprint(billing_bp)
