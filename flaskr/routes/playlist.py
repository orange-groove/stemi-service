from flask import Flask, Blueprint, request, jsonify

from flaskr.database_functions.playlist import (
    create_playlist,
    get_playlists,
    update_playlist,
    delete_playlist,
    get_playlist_songs,
    get_playlist,
    add_song_to_playlist,
    remove_song_from_playlist,
    get_playlist_song_count
)

from flaskr.decorators.auth import authorize

app = Flask(__name__)

playlist_bp = Blueprint('playlist_bp', __name__)

@playlist_bp.route('/playlist', methods=['POST'])
@authorize
def create_playlist_route():

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    user_id = getattr(request, 'user_id', None)

    print(f"Creating playlist: data={data}, user_id={user_id}")  # Debug log
    
    if not user_id or not data:
        return jsonify({"error": "Both 'user_id' and 'data' are required."}), 400
    
    data['user_id'] = user_id
    playlist = create_playlist(data)

    return jsonify({
        "message": "Playlist created successfully",
        "playlist": playlist,
    }), 200


@playlist_bp.route('/playlist', methods=['GET'])
@authorize
def get_playlists_route():
    user_id = getattr(request, 'user_id', None)
    
    if not user_id :
        return jsonify({"error": "'user_id' is required."}), 400
    
    playlists = get_playlists(user_id)

    return jsonify({
        "playlists": playlists,
        "message": "Playlists fetched successfully",
    }), 200

@playlist_bp.route('/playlist/<playlist_id>', methods=['GET'])
@authorize
def get_playlist_route(playlist_id):
    playlist = get_playlist(playlist_id)

    return jsonify({
        "playlist": playlist,
        # "message": "Playlist fetched successfully",
    }), 200


@playlist_bp.route('/playlist/<playlist_id>', methods=['PUT'])
@authorize
def update_playlist_route(playlist_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    
    playlist = update_playlist(playlist_id, data)

    return jsonify({
        "message": "Playlist updated successfully",
        "playlist": playlist,
    }), 200


@playlist_bp.route('/playlist/<playlist_id>/song', methods=['GET'])
@authorize
def get_playlist_songs_route(playlist_id):

    if not playlist_id:
        return jsonify({"error": "'playlist_id' is required."}), 400
    
    songs = get_playlist_songs(playlist_id)

    return jsonify({
        # "message": "Playlist songs fetched successfully",
        "songs": songs,
    }), 200


@playlist_bp.route('/playlist/<playlist_id>', methods=['DELETE'])
@authorize
def delete_playlist_route(playlist_id):
    playlist = delete_playlist(playlist_id)

    return jsonify({
        "message": "Playlist deleted successfully",
        "playlist": playlist,
    }), 200


@playlist_bp.route('/playlist/<playlist_id>/song/<song_id>', methods=['POST'])
@authorize
def add_song_to_playlist_route(playlist_id, song_id):
    """
    POST endpoint to add song to playlist.
    """
    try:

        if not playlist_id or not song_id:
            return jsonify({"error": "Missing required parameters"}), 400

        # Add song to playlist
        updated_song = add_song_to_playlist(song_id, playlist_id)

        return jsonify({
            "song": updated_song,
            "message": "Song added to playlist successfully",
        }), 200
    
    except Exception as e:
        if (e.code == '23505'):
            return jsonify({"error": "Song already added to playlist"}), 409
        return jsonify({"error": str(e)}), 500
    
@playlist_bp.route('/playlist/<playlist_id>/song/<song_id>', methods=['DELETE'])
@authorize
def remove_song_from_playlist_route(playlist_id, song_id):
    """
    DELETE endpoint to remove song from playlist.
    """
    try:

        if not playlist_id or not song_id:
            return jsonify({"error": "Missing required parameters"}), 400

        # Remove song from playlist
        removed_song = remove_song_from_playlist(song_id, playlist_id)

        return jsonify({
            "song": removed_song,
            "message": "Song removed from playlist successfully",
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

