import os
from flask import Flask, Blueprint, request, jsonify
from flaskr.utils.helpers import (
    get_song_info,
)

from flaskr.database_functions.song import (
    get_song,
    get_user_songs,
    delete_song,
    update_song,
)

from flaskr.decorators.auth import authorize

app = Flask(__name__)

song_bp = Blueprint('song_bp', __name__)

@song_bp.route('/song', methods=['GET'])
@authorize
def get_user_songs_route():
    user_id = getattr(request, 'user_id', None)
    songs = get_user_songs(user_id)

    return jsonify({
        "songs": songs,
    }), 200


@song_bp.route('/song/<song_id>', methods=['GET'])
@authorize
def get_song_route(song_id):
    song = get_song(song_id)

    return jsonify({
        "song": song,
        "message": "Song fetched successfully",
    }), 200


@song_bp.route('/song/<song_id>', methods=['DELETE'])
@authorize
def delete_song_route(song_id):
    song = delete_song(song_id)

    return jsonify({
        "song": song,
        "message": "Song deleted successfully",
    }), 200


@song_bp.route('/song/<song_id>', methods=['PUT'])
@authorize
def update_song_route(song_id):
    try:
        # Parse JSON body
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400

        title = data.get('title')
        artist = data.get('artist')

        song = {}
        if title:
            song['title'] = title
        if artist:
            song['artist'] = artist

        # Ensure there's something to update
        if not song:
            return jsonify({"error": "No fields to update"}), 400

        updated_song = update_song(song_id, song)

        return jsonify({
            "song": updated_song,
            "message": "Song updated successfully",
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/song/info', methods=['GET'])
def song_info(user_id):
    artist = request.args.get('artist')
    name = request.args.get('name')
    
    if not artist or not name:
        return jsonify({"error": "Both 'artist' and 'song' query parameters are required."}), 400

    info = get_song_info(artist, name)
    # popups = get_popup_info(artist, name)
    
    return jsonify({"user_id": user_id, "artist": artist, "name": name, "info": info}), 200
