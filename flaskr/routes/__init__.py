from flask import Blueprint
from .playlist import playlist_bp
from .song import song_bp

routes_bp = Blueprint('api/v1', __name__)

routes_bp.register_blueprint(playlist_bp)
routes_bp.register_blueprint(song_bp)
