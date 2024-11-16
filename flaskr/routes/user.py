import os
from flask import Flask, Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from flaskr.utils.helpers import (
    separate, 
    create_song_entry,
    upload_song_stems_and_update_db, 
    get_song_info,
    cleanup_temp_files,
    recognize_song,
)

app = Flask(__name__)

user_bp = Blueprint('user_bp', __name__)
UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')


@user_bp.route('/<user_id>/playlist/<playlist_id>/song', methods=['POST'])
def upload_song(user_id, playlist_id):
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
        song_entry = create_song_entry(user_id=user_id, playlist_id=playlist_id)

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
 
        file_path = os.path.join(UPLOAD_FOLDER, str(song_entry.get('id')) + '.mp3')
        file.save(file_path)

        output_path = os.path.join(OUTPUT_FOLDER, str(song_entry.get('id')))
        os.makedirs(output_path, exist_ok=True)

        # Recognize the song
        recognized_song = recognize_song(file_path)

        artist = recognized_song.get('result').get('artist')
        title = recognized_song.get('result').get('title')

        song_entry['artist'] = artist
        song_entry['title'] = title
        song_entry['album'] = recognized_song.get('result').get('album')
        song_entry['release_date'] = recognized_song.get('result').get('release_date')
        song_entry['image_url'] = recognized_song.get('result').get('spotify').get('album').get('images')[1].get('url')

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

@user_bp.route('/<user_id>/song/info', methods=['GET'])
def song_info(user_id):
    artist = request.args.get('artist')
    name = request.args.get('name')
    
    if not artist or not name:
        return jsonify({"error": "Both 'artist' and 'song' query parameters are required."}), 400

    info = get_song_info(artist, name)
    # popups = get_popup_info(artist, name)
    
    return jsonify({"user_id": user_id, "artist": artist, "name": name, "info": info}), 200
