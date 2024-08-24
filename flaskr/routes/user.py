from flask import Blueprint, request, jsonify
import os
from werkzeug.utils import secure_filename
from flaskr.utils.helpers import separate, create_song_entry, upload_song_stems_and_update_db

user_bp = Blueprint('user_bp', __name__)

# Configure the upload and output folders
UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')

@user_bp.route('/<user_id>/song', methods=['POST'])
def upload_song(user_id):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    name = request.form.get('name')
    description = request.form.get('description')
    stems = request.form.get('stems')
    algorithm = request.form.get('algorithm', 'htdemucs')
    file = request.files['file']
    
    if not name or not description:
        return jsonify({"error": "Missing name or description"}), 400
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        song_name = os.path.splitext(filename)[0]
        user_folder = os.path.join(UPLOAD_FOLDER, user_id)
        os.makedirs(user_folder, exist_ok=True)

        file_path = os.path.join(user_folder, filename)
        file.save(file_path)

        # Prepare the output path
        output_path = os.path.join(OUTPUT_FOLDER, user_id, song_name)
        os.makedirs(output_path, exist_ok=True)

        # Call the separate utility to process the song
        separate(file_path, output_path, algorithm)

        # Create song entry in the database
        song_entry = create_song_entry(name, description, user_id)
        
        # Upload stems to Supabase and update the database
        stem_names = ['vocals', 'bass', 'drums', 'other']  # Example stem names
        updated_song_entry = upload_song_stems_and_update_db(song_entry, output_path, stem_names)

        return jsonify({
            "message": "File uploaded, processed, and saved successfully",
            "song_entry": updated_song_entry
        }), 200
