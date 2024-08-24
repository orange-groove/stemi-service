from flask import Blueprint
from .user import user_bp

routes_bp = Blueprint('api/v1', __name__)

routes_bp.register_blueprint(user_bp, url_prefix='/user')

@routes_bp.route('/healthz', methods=['GET'])
def healthz():
    return 'Ok'