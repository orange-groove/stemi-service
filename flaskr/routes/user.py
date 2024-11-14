import os
from flask import Flask, Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from flaskr.utils.helpers import (
    separate, 
    create_song_entry,
    upload_song_stems_and_update_db, 
    get_song_info,
    cleanup_temp_files,
)

app = Flask(__name__)

user_bp = Blueprint('user_bp', __name__)
UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')


@user_bp.route('/<user_id>/playlist/<playlist_id>/song', methods=['POST'])
def upload_song(user_id, playlist_id):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    name = request.form.get('name')
    artist = request.form.get('artist')
    algorithm = request.form.get('algorithm', 'htdemucs_6s')
    file = request.files['file']
    
    if not playlist_id:
        return jsonify({"error": "Missing playlist id"}), 400
    
    if not name or not artist:
        return jsonify({"error": "Missing name or artist"}), 400
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        song_name = os.path.splitext(filename)[0]
        user_folder = os.path.join(UPLOAD_FOLDER, user_id)
        os.makedirs(user_folder, exist_ok=True)

        file_path = os.path.join(user_folder, filename)
        file.save(file_path)

        output_path = os.path.join(OUTPUT_FOLDER, user_id, song_name)
        os.makedirs(output_path, exist_ok=True)

        # Separate the stems
        separate(file_path, output_path, algorithm)

        # Analyze the combined audio
        # analyzed_audio_data = analyze_audio(file_path)
        # key_changes = analyzed_audio_data['key_changes']
        # tempo_changes = analyzed_audio_data['tempo_changes']

        # Create song entry in the database
        song_entry = create_song_entry(name, artist, user_id, playlist_id)
        
        # Upload stems to Supabase and update the database
        stem_names = ['vocals', 'bass', 'drums', 'guitar', 'other']
        updated_song_entry = upload_song_stems_and_update_db(song_entry, output_path, stem_names)

        # Cleanup temporary files
        cleanup_temp_files(file_path)

        return jsonify({
            "message": "File uploaded, processed, and saved successfully",
            "song_entry": updated_song_entry,
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
