import os

from flask import Flask, Blueprint, request, jsonify, send_file
from flaskr.supabase_client import supabase
from flaskr.utils.helpers import (
    download_stems_zip,
    mix_and_zip_stems,
    separate_with_runpod,
    cleanup_temp_files,
    cleanup_expired_sessions,
    check_usage_limit,
    increment_user_usage,
    get_user_monthly_usage,
    get_user_monthly_limit,
    is_user_premium,
    get_current_month_year,
)

from flaskr.decorators.auth import authorize

app = Flask(__name__)

song_bp = Blueprint('song_bp', __name__)


def validate_session_access(session_id, user_id):
    """
    Validate that the user has access to the session.
    Returns (is_valid, session_metadata) tuple.
    """
    import glob
    import json
    
    # Find the temporary output directory for this session
    import tempfile
    temp_base = tempfile.gettempdir()
    temp_dirs = glob.glob(f"{temp_base}/output_{session_id}_*")
    
    print(f"Looking for session {session_id}, found temp dirs: {temp_dirs}")
    print(f"Searching in temp base: {temp_base}")
        
    if not temp_dirs:
        print(f"No temp directories found for session {session_id}")
        return False, None
        
    output_path = temp_dirs[0]
    metadata_file = os.path.join(output_path, "session_metadata.json")
    print(f"Looking for metadata file: {metadata_file}")
    
    if not os.path.exists(metadata_file):
        print(f"Metadata file not found: {metadata_file}")
        return False, None
        
    # Load session metadata
    try:
        with open(metadata_file, 'r') as f:
            session_metadata = json.load(f)
        
        print(f"Loaded session metadata: {session_metadata}")
        
        # Check if user owns this session
        if session_metadata.get('user_id') != user_id:
            print(f"User ID mismatch: expected {user_id}, got {session_metadata.get('user_id')}")
            return False, None
            
        return True, session_metadata
    except Exception as e:
        print(f"Error loading session metadata: {e}")
        return False, None


@song_bp.route('/process', methods=['POST'])
@authorize
def process_song():
    """
    Process a song file or YouTube URL and return session info for preview and download.
    Session data persists until explicitly deleted by frontend.
    """
    import uuid
    import tempfile
    import json
    
    # Get user ID from auth decorator
    user_id = getattr(request, 'user_id', None)
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401
    
    # Check usage limits before processing
    usage_check = check_usage_limit(user_id)
    if not usage_check['can_process']:
        return jsonify({
            "error": "Monthly usage limit exceeded",
            "current_usage": usage_check['current_usage'],
            "monthly_limit": usage_check['monthly_limit'],
            "is_premium": usage_check['is_premium'],
            "message": f"You have reached your monthly limit of {usage_check['monthly_limit']} songs. {'Upgrade to premium for more processing.' if not usage_check['is_premium'] else 'Your limit resets next month.'}"
        }), 429  # Too Many Requests
    
    # Generate unique session ID for this processing request
    session_id = str(uuid.uuid4())
    
    # Check for a YouTube URL or file upload
    youtube_url = request.form.get('youtube_url')
    file = request.files.get('file')

    if not youtube_url and not file:
        return jsonify({"error": "No file or YouTube URL provided"}), 400

    # Create temporary directories for this session
    temp_upload_dir = tempfile.mkdtemp(prefix=f"upload_{session_id}_")
    temp_output_dir = tempfile.mkdtemp(prefix=f"output_{session_id}_")
    
    try:
        # Set file paths
        file_path = os.path.join(temp_upload_dir, f"input.wav")
        output_path = temp_output_dir

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        try:
            print(f"Saving uploaded file to: {file_path}")
            file.save(file_path)
            print(f"WAV file saved to: {file_path}")
        except Exception as e:
            return jsonify({"error": "Failed to save file"}), 500

        # Process the song - separate stems using RunPod
        try:
            print(f"Starting stem separation for {file_path} -> {output_path}")
            separation_result = separate_with_runpod(file_path, output_path)
            print("Stem separation completed successfully.")
            print(f"Separation result: {separation_result}")
        except Exception as e:
            print(f"Stem separation failed: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": "Failed during stem separation processing"}), 500

        # Store session metadata in a simple JSON file for persistence
        available_stems = separation_result.get("available_stems", ['vocals', 'bass', 'drums', 'guitar', 'piano', 'other'])
        session_metadata = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            "available_stems": available_stems,
            "output_path": output_path,
            "upload_path": temp_upload_dir
        }
        
        # Save session metadata
        metadata_file = os.path.join(temp_output_dir, "session_metadata.json")
        print(f"Creating metadata file: {metadata_file}")
        with open(metadata_file, 'w') as f:
            json.dump(session_metadata, f)
        print(f"Metadata file created successfully")
        
        # Verify the metadata file exists
        if os.path.exists(metadata_file):
            print(f"Metadata file verified to exist: {metadata_file}")
        else:
            print(f"ERROR: Metadata file not found after creation: {metadata_file}")

        # Clean up upload directory (we only need the output stems)
        cleanup_temp_files(temp_upload_dir)
        print(f"Cleaned up upload directory: {temp_upload_dir}")
        print(f"Output directory still exists: {temp_output_dir}")

        # Record session in Supabase for scheduled cleanup of storage
        try:
            # Bucket is 'stems'; objects live under '<session_id>/'
            storage_prefix = session_id
            supabase.table('sessions').insert({
                'session_id': session_id,
                'user_id': user_id,
                'storage_prefix': storage_prefix,
            }).execute()
        except Exception as e:
            print(f"Warning: failed to record session in DB: {e}")

        # Increment user's monthly usage count
        increment_success = increment_user_usage(user_id)
        if not increment_success:
            print(f"Warning: failed to increment usage count for user {user_id}")

        response_data = {
            "session_id": session_id,
            "message": "Song processed successfully",
            "preview_url": f"/api/v1/session/{session_id}/preview",
            "download_endpoints": {
                "stems": f"/api/v1/download/stems/{session_id}",
                "mixdown": f"/api/v1/download/mixdown/{session_id}"
            },
            "cleanup_url": f"/api/v1/session/{session_id}"
        }

        return jsonify(response_data), 200
        
    except Exception as e:
        # Cleanup on error - only clean up upload directory, keep output for debugging
        cleanup_temp_files(temp_upload_dir)
        # Don't clean up temp_output_dir here - let it persist for debugging
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500
    


@song_bp.route('/session/<session_id>/preview', methods=['GET'])
@authorize
def get_session_preview(session_id):
    """
    GET endpoint to retrieve session preview information for the multitrack player.
    """
    try:
        # Get user ID from auth decorator
        user_id = getattr(request, 'user_id', None)
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401
        
        # Validate session access
        is_valid, session_metadata = validate_session_access(session_id, user_id)
        if not is_valid:
            return jsonify({"error": "Session not found or access denied"}), 404
        
        # Return preview information for the multitrack player
        preview_data = {
            "session_id": session_id,
            "available_stems": session_metadata.get("available_stems", []),
            "stem_urls": {
                stem: f"/api/v1/session/{session_id}/stem/{stem}" 
                for stem in session_metadata.get("available_stems", [])
            }
        }
        
        return jsonify(preview_data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/session/<session_id>/stem/<stem_name>', methods=['GET'])
@authorize
def get_stem_audio(session_id, stem_name):
    """
    GET endpoint to serve individual stem audio files for preview.
    """
    try:
        # Get user ID from auth decorator
        user_id = getattr(request, 'user_id', None)
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401
        
        # Validate session access
        is_valid, session_metadata = validate_session_access(session_id, user_id)
        if not is_valid:
            return jsonify({"error": "Session not found or access denied"}), 404
        
        # Get the output path from session metadata
        output_path = session_metadata.get("output_path")
        stem_file = os.path.join(output_path, f"{stem_name}.wav")
        
        if not os.path.exists(stem_file):
            return jsonify({"error": f"Stem '{stem_name}' not found"}), 404
        
        return send_file(stem_file, mimetype='audio/wav')

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/download/stems/<session_id>', methods=['POST'])
@authorize
def download_stems(session_id):
    """
    POST endpoint to generate and download a ZIP file of stems for a session.
    Expects JSON body with 'stems' and 'file_type' parameters.
    """
    try:
        # Get user ID from auth decorator
        user_id = getattr(request, 'user_id', None)
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401
        
        # Parse JSON request body
        data = request.get_json()
        stems = data.get('stems', [])
        file_type = data.get('file_type', 'wav')

        if not stems or not session_id:
            return jsonify({"error": "Missing required parameters"}), 400

        # Validate session access
        is_valid, session_metadata = validate_session_access(session_id, user_id)
        if not is_valid:
            return jsonify({"error": "Session not found or access denied"}), 404
        
        # Get the output path from session metadata
        output_path = session_metadata.get("output_path")
        
        # Generate ZIP file using the temporary output directory
        zip_file_path = download_stems_zip(stems, file_type, session_id, output_path)

        # Return ZIP file as a response
        return send_file(
            zip_file_path,
            as_attachment=True,
            download_name=f"Stems_{session_id}.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/download/mixdown/<session_id>', methods=['POST'])
@authorize
def mixdown_song(session_id):
    """
    POST endpoint to mix selected stems into a single audio file and return a ZIP.

    Expects JSON body with 'stems' and optional 'file_type' parameters.
    """
    try:
        # Get user ID from auth decorator
        user_id = getattr(request, 'user_id', None)
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401
        
        # Parse JSON request body
        data = request.get_json()
        stems = data.get('stems', [])
        file_type = data.get('file_type', 'mp3')

        if not stems or not session_id:
            return jsonify({"error": "Missing required parameters"}), 400

        # Validate session access
        is_valid, session_metadata = validate_session_access(session_id, user_id)
        if not is_valid:
            return jsonify({"error": "Session not found or access denied"}), 404
        
        # Get the output path from session metadata
        output_path = session_metadata.get("output_path")

        # Mix and create ZIP using the temporary output directory
        zip_file_path = mix_and_zip_stems(stems, session_id, file_type, output_path)

        # Return ZIP file as a response
        return send_file(
            zip_file_path,
            as_attachment=True,
            download_name=f"Mixdown_{session_id}.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/session/<session_id>', methods=['DELETE'])
@authorize
def cleanup_session(session_id):
    """
    DELETE endpoint to clean up session data when frontend is done.
    """
    try:
        # Get user ID from auth decorator
        user_id = getattr(request, 'user_id', None)
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401
        
        # Validate session access
        is_valid, session_metadata = validate_session_access(session_id, user_id)
        if not is_valid:
            return jsonify({"error": "Session not found or access denied"}), 404
        
        # Get the output path from session metadata
        output_path = session_metadata.get("output_path")
        
        # Clean up the session directory
        cleanup_temp_files(output_path)
        
        return jsonify({
            "message": "Session cleaned up successfully",
            "session_id": session_id
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@song_bp.route('/cleanup', methods=['POST'])
def cleanup_endpoint():
    """
    POST endpoint to trigger cleanup of expired sessions.
    Optional query param: hours (default 24)
    Intended to be called by Supabase cron/Scheduler.
    """
    try:
        hours = request.args.get('hours', default=24, type=int)
        cleanup_expired_sessions(max_age_hours=hours)
        return jsonify({"message": "Cleanup completed", "max_age_hours": hours}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@song_bp.route('/usage', methods=['GET'])
@authorize
def get_usage():
    """
    Get current user's monthly usage and limits.
    """
    user_id = getattr(request, 'user_id', None)
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401
    
    try:
        usage_info = check_usage_limit(user_id)
        
        return jsonify({
            "current_usage": usage_info['current_usage'],
            "monthly_limit": usage_info['monthly_limit'], 
            "remaining": usage_info['remaining'],
            "can_process": usage_info['can_process'],
            "is_premium": usage_info['is_premium'],
            "month": get_current_month_year()
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get usage info: {str(e)}"}), 500

