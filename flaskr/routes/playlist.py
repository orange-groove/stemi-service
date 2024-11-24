import os
from flask import Flask, Blueprint, request, jsonify
from flaskr.utils.helpers import (
    separate, 
    cleanup_temp_files,
    recognize_song,

)

from flaskr.database_functions.playlist import (
    create_playlist,
    get_playlists,
    update_playlist,
    delete_playlist,
    get_playlist_songs,
    get_playlist
)

from flaskr.database_functions.song import (
    create_song,
    upload_song_stems_and_update_db
)


from flaskr.decorators.auth import authorize

app = Flask(__name__)

playlist_bp = Blueprint('playlist_bp', __name__)
UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')


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


@playlist_bp.route('/playlist/<playlist_id>/song', methods=['POST'])
@authorize
def upload_song(playlist_id):
    user_id = getattr(request, 'user_id', None)

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    algorithm = request.form.get('algorithm', 'htdemucs_6s')
    file = request.files['file']
    
    if not playlist_id:
        return jsonify({"error": "Missing playlist id"}), 400
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        # Create song entry immediately to get the song id
        song_entry = create_song({'playlist_id': playlist_id, 'user_id': user_id})

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
 
        file_path = os.path.join(UPLOAD_FOLDER, str(song_entry.get('id')) + '.mp3')
        file.save(file_path)

        output_path = os.path.join(OUTPUT_FOLDER, str(song_entry.get('id')))
        os.makedirs(output_path, exist_ok=True)

        # Recognize the song
        recognized_song = recognize_song(file_path).get('result')

        if recognized_song:
            song_entry['artist'] = recognized_song.get('artist')
            song_entry['title'] = recognized_song.get('title')
            song_entry['album'] = recognized_song.get('album')
            song_entry['release_date'] = recognized_song.get('release_date')
            song_entry['image_url'] = recognized_song.get('spotify').get('album').get('images')[1].get('url')

        # Separate the stems
        separate(file_path, output_path, algorithm)
        
        # Upload stems to Supabase and update the database
        stem_names = ['vocals', 'bass', 'drums', 'guitar', 'other']
        upload_song_stems_and_update_db(song_entry, output_path, stem_names)

        # Cleanup temporary files
        cleanup_temp_files(file_path)
        cleanup_temp_files(output_path)

        return jsonify({
            "message": "File uploaded, processed, and saved successfully",
        }), 200
