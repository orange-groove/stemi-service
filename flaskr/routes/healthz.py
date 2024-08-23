from flask import Blueprint
songs_bp = Blueprint('songs', __name__)
from flask import Flask, jsonify

app = Flask(__name__)

@songs_bp.route('/healthz', methods=['GET'])
def healthz():
    return 'Ok'
