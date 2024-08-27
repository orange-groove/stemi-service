from flask import Flask, Blueprint, request, jsonify
import os
import librosa
import soundfile as sf
import numpy as np
from werkzeug.utils import secure_filename
from flaskr.utils.helpers import (
    separate, 
    create_song_entry, 
    upload_song_stems_and_update_db, 
    analyze_audio
)
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=2)  # Adjust number of workers as needed

app = Flask(__name__)

user_bp = Blueprint('user_bp', __name__)
UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')

@user_bp.route('/<user_id>/song', methods=['POST'])
def upload_song(user_id):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    name = request.form.get('name')
    artist = request.form.get('artist')
    stems = request.form.get('stems')
    algorithm = request.form.get('algorithm', 'htdemucs')
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
        drum_path = os.path.join(output_path, 'drums.mp3')
        bass_path = os.path.join(output_path, 'bass.mp3')
        other_path = os.path.join(output_path, 'other.mp3')
        
        combined_audio_path = os.path.join(output_path, "combined_no_vocals.wav")

        combined_audio_data = None

        # Load and combine the drum, bass, and other stems (excluding vocals)
        for stem_path in [drum_path, bass_path, other_path]:
            y, sr = librosa.load(stem_path, sr=None)

            if combined_audio_data is None:
                combined_audio_data = y
            else:
                combined_audio_data += y

        if combined_audio_data is not None:
            combined_audio_data /= 3  # Normalize the combined signal
            sf.write(combined_audio_path, combined_audio_data, sr)

        # Analyze the combined audio without vocals
        analyzed_audio_data = analyze_audio(combined_audio_path)
        key_changes = analyzed_audio_data['key_changes']
        tempo_changes = analyzed_audio_data['tempo_changes']

        # Create song entry in the database
        song_entry = create_song_entry(name, artist, user_id)
        
        # Upload stems to Supabase and update the database
        stem_names = ['vocals', 'bass', 'drums', 'other']  # Example stem names
        updated_song_entry = upload_song_stems_and_update_db(song_entry, output_path, stem_names, key_changes, tempo_changes)

        return jsonify({
            "message": "File uploaded, processed, and saved successfully",
            "song_entry": updated_song_entry,
        }), 200
