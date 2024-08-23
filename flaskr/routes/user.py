from flask import Blueprint, request, jsonify
from pathlib import Path
from shutil import rmtree
import os
from flaskr.utils.supabase_utils import supabase, upload_to_supabase, get_public_url, generate_directory_name
from flaskr.utils.helpers import separate

from flask import Flask, jsonify, abort
from flaskr.utils.supabase_utils import list_tracks_for_song

songs_bp = Blueprint('user', __name__)
app = Flask(__name__)

@app.route('<user_id>/song/<song_id>/tracks', methods=['GET'])
def get_tracks(song_id):
    # Retrieve the tracks from Supabase
    tracks = list_tracks_for_song(song_id)
    
    if tracks is None:
        return abort(404, description="Song ID not found or no tracks available")
    
    return jsonify({
        "name": "test",
        "tracks": tracks
    })

if __name__ == '__main__':
    app.run(debug=True)

@songs_bp.route('<user_id>/song', methods=['POST'])
def upload_song():
    user_name = "default_user"  # Replace this with actual user identification logic
    directory_name = generate_directory_name(user_name)
    
    in_path = Path('tmp_in')
    out_path = Path('tmp_out')
    
    if in_path.exists():
        rmtree(in_path)
    in_path.mkdir()
    
    if out_path.exists():
        rmtree(out_path)
    out_path.mkdir()

    uploaded_files = request.files.getlist('file')
    
    for uploaded_file in uploaded_files:
        file_path = in_path / uploaded_file.filename
        uploaded_file.save(file_path)

    # Replace this with your actual separation logic
    separate(in_path, out_path)
    
    # Upload each separated track to Supabase and collect the URLs
    track_urls = []
    for root, dirs, files in os.walk(out_path):
        for file in files:
            file_path = Path(root) / file
            storage_path = f"{directory_name}/{file_path.name}"
            upload_to_supabase(str(file_path), storage_path)
            public_url = get_public_url(storage_path)
            track_urls.append({'name': file, 'url': public_url})
    
    return jsonify({"tracks": track_urls})

@songs_bp.route('/<user_id>/songs', methods=['GET'])
def get_user_songs(user_id):
    response = supabase.table('user_songs').select("*").eq("user_id", user_id).execute()
    
    if response.status_code != 200:
        return jsonify({"error": "Error fetching songs"}), response.status_code
    
    return jsonify({"songs": response.data})