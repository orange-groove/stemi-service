import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from flask import Flask, Blueprint, request, jsonify, send_file
from flaskr.utils.helpers import (
    download_stems_zip,
    mix_and_zip_stems,
    separate, 
    cleanup_temp_files,
    analyze_song,
    youtube_to_audio
)

from flaskr.database_functions.song import (
    get_song,
    get_user_songs,
    delete_song,
    update_song,
    create_song,
    upload_song_stems_and_update_db,
)

from flaskr.decorators.auth import authorize

app = Flask(__name__)

song_bp = Blueprint('song_bp', __name__)

UPLOAD_FOLDER = os.path.expanduser('~/tmp_uploads')
OUTPUT_FOLDER = os.path.expanduser('~/tmp_output')

@song_bp.route('/song', methods=['POST'])
@authorize
def upload_song():
    user_id = getattr(request, 'user_id', None)

    # Check for a YouTube URL or file upload
    youtube_url = request.form.get('youtube_url')
    file = request.files.get('file')

    if not youtube_url and not file:
        return jsonify({"error": "No file or YouTube URL provided"}), 400

    # Create song entry immediately to get the song id
    song_entry = create_song({'user_id': user_id})

    # Ensure upload and output directories exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Set file paths
    file_path = os.path.join(UPLOAD_FOLDER, f"{song_entry.get('id')}.wav")

    # Handle file upload or YouTube URL
    if youtube_url:
        try:
            print(f"Downloading YouTube audio from: {youtube_url}")
            youtube_to_audio(youtube_url, file_path)
            print(f"WAV file saved to: {file_path}")
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    elif file:
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        try:
            print(f"Saving uploaded file to: {file_path}")
            file.save(file_path)
            print(f"WAV file saved to: {file_path}")
        except Exception as e:
            return jsonify({"error": "Failed to save file"}), 500

    # Set output path for separated stems
    output_path = os.path.join(OUTPUT_FOLDER, str(song_entry.get('id')))
    os.makedirs(output_path, exist_ok=True)

    # Prepare to run tasks in parallel
    tasks = {
        "separate": (separate, (file_path, output_path)),
        "analyze_song": (analyze_song, (file_path,))
    }

    results = {}
    try:
        with ProcessPoolExecutor() as executor:
            future_to_task = {executor.submit(func, *args): name for name, (func, args) in tasks.items()}
            for future in as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    results[task_name] = future.result()
                    print(f"Task '{task_name}' completed successfully.")
                except Exception as exc:
                    print(f"Task '{task_name}' failed: {exc}")
                    return jsonify({"error": f"Failed during {task_name} processing"}), 500

    except Exception as e:
        print(f"Parallel task execution failed: {e}")
        return jsonify({"error": "Failed to process tasks in parallel"}), 500

    # Update song entry with analysis results
    analyzed_song = results.get("analyze_song")
    if analyzed_song:
        song_entry['tempo_changes'] = analyzed_song.get('tempo_changes')
        song_entry['song_key'] = analyzed_song.get('song_key')

    # Upload stems to Supabase and update the database
    stem_names = ['vocals', 'bass', 'drums', 'guitar', 'piano', 'other']
    upload_song_stems_and_update_db(song_entry, output_path, stem_names)

    # Cleanup temporary files
    cleanup_temp_files(file_path)
    cleanup_temp_files(output_path)

    return jsonify({
        "song": song_entry,
        "message": "File uploaded, processed, and saved successfully",
    }), 200
    

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

@song_bp.route('/song/sample', methods=['GET'])
def get_sample_song_route():
    song = get_song(402) # Sample song ID

    return jsonify({
        "song": song,
        "message": "Song fetched successfully",
    }), 200

@song_bp.route('/song/<song_id>', methods=['DELETE'])
@authorize
def delete_song_route(song_id):
    user_id = getattr(request, 'user_id', None)
    song = delete_song(user_id, song_id)

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


# @song_bp.route('/song/info', methods=['GET'])
# def song_info(user_id):
#     artist = request.args.get('artist')
#     name = request.args.get('name')
    
#     if not artist or not name:
#         return jsonify({"error": "Both 'artist' and 'song' query parameters are required."}), 400

#     info = get_song_info(artist, name)
#     # popups = get_popup_info(artist, name)
    
#     return jsonify({"user_id": user_id, "artist": artist, "name": name, "info": info}), 200


@song_bp.route('/song/<song_id>/download_stems', methods=['POST'])
@authorize
def download_stems(song_id):
    """
    POST endpoint to generate and download a ZIP file of stems.
    Expects JSON body with 'stems' and 'file_type' parameters.
    """
    try:
        # Parse JSON request body
        data = request.get_json()
        stems = data.get('stems', [])
        file_type = data.get('file_type')

        if not stems or not file_type or not song_id:
            return jsonify({"error": "Missing required parameters"}), 400

        # Generate ZIP file
        zip_file_path = download_stems_zip(stems, file_type, song_id)


        # Return ZIP file as a response
        return send_file(
            zip_file_path,
            as_attachment=True,
            download_name=f"Song_{song_id}_stems.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/song/<song_id>/download_mixdown', methods=['POST'])
@authorize
def mixdown_song(song_id):
    """
    POST endpoint to mix selected stems into a single audio file and return a ZIP.

    Expects JSON body with 'stems' and optional 'file_type' parameters.
    """
    try:
        # Parse JSON request body
        data = request.get_json()
        stems = data.get('stems', [])
        file_type = data.get('file_type', 'mp3')

        if not stems or not song_id:
            return jsonify({"error": "Missing required parameters"}), 400

        # Mix and create ZIP
        zip_file_path = mix_and_zip_stems(stems, song_id, file_type)

        # Return ZIP file as a response
        return send_file(
            zip_file_path,
            as_attachment=True,
            download_name=f"Song_{song_id}_mixdown.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


