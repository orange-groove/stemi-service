from flask import Blueprint
from .auth import auth_bp
from .songs import songs_bp

routes_bp = Blueprint('api/v1', __name__)

routes_bp.register_blueprint(auth_bp, url_prefix='/auth')
routes_bp.register_blueprint(songs_bp, url_prefix='/songs')

@routes_bp.route('/healthz', methods=['GET'])
def healthz():
    return 'Ok'