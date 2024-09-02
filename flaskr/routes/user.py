from flask import Flask, Blueprint, request, jsonify
import os
import librosa
import soundfile as sf
from werkzeug.utils import secure_filename
from flaskr.utils.helpers import (
    separate, 
    create_song_entry, 
    upload_song_stems_and_update_db, 
    analyze_audio,
    get_song_info
)
import shutil

app = Flask(__name__)

user_bp = Blueprint('user_bp', __name__)
UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')

def process_audio_files(stem_paths, combined_audio_path):
    """Combine audio files by loading them in chunks to reduce memory usage."""
    combined_audio_data = None
    sr = None
    for stem_path in stem_paths:
        y, sr = librosa.load(stem_path, sr=None)
        if combined_audio_data is None:
            combined_audio_data = y
        else:
            combined_audio_data += y
    if combined_audio_data is not None and sr is not None:
        combined_audio_data /= len(stem_paths)  # Normalize
        sf.write(combined_audio_path, combined_audio_data, sr)

def cleanup_temp_files(*paths):
    """Delete temporary files and directories."""
    for path in paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

@user_bp.route('/<user_id>/song', methods=['POST'])
def upload_song(user_id):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    name = request.form.get('name')
    artist = request.form.get('artist')
    algorithm = request.form.get('algorithm', 'hybrid')
    file = request.files['file']
    
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

        # Paths to the generated stems
        bass_path = os.path.join(output_path, 'bass.mp3')
        other_path = os.path.join(output_path, 'other.mp3')
        combined_audio_path = os.path.join(output_path, "combined_no_vocals.wav")

        # Combine audio files
        process_audio_files([bass_path, other_path], combined_audio_path)

        # Analyze the combined audio
        analyzed_audio_data = analyze_audio(combined_audio_path)
        key_changes = analyzed_audio_data['key_changes']
        tempo_changes = analyzed_audio_data['tempo_changes']

        # Create song entry in the database
        song_entry = create_song_entry(name, artist, user_id)
        
        # Upload stems to Supabase and update the database
        stem_names = ['vocals', 'bass', 'drums', 'other']
        updated_song_entry = upload_song_stems_and_update_db(song_entry, output_path, stem_names, key_changes, tempo_changes)

        # Cleanup temporary files
        cleanup_temp_files(file_path, combined_audio_path)

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
    
    return jsonify({"user_id": user_id, "artist": artist, "name": name, "info": info})
