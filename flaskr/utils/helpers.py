import os
import shutil
from flaskr.supabase_client import supabase
import logging
# from openai import OpenAI
import json
from flaskr.config import Config
import requests
import tempfile
import zipfile
from pydub import AudioSegment
from yt_dlp import YoutubeDL
import base64
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)
# Initialize OpenAI client
# client = OpenAI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

logger = logging.getLogger(__name__)


def encode_audio_to_base64(file_path):
    """
    Encode an audio file to base64 string for RunPod API.
    
    Args:
        file_path (str): Path to the audio file
        
    Returns:
        str: Base64 encoded audio file
    """
    try:
        with open(file_path, "rb") as audio_file:
            audio_data = audio_file.read()
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            return audio_b64
    except Exception as e:
        logger.error(f"Error encoding audio file to base64: {e}")
        raise


def submit_to_runpod(audio_b64, stems=None):
    """
    Submit audio separation job to RunPod API.
    
    Args:
        audio_b64 (str): Base64 encoded audio file
        stems (list): List of stems to separate (default: all available)
        
    Returns:
        str: Job ID for tracking the separation
    """
    if not Config.RUNPOD_API_KEY:
        raise ValueError("RUNPOD_API_KEY not configured")
    
    if stems is None:
        stems = ["vocals", "drums", "bass", "guitar", "piano", "other"]
    
    url = f"https://api.runpod.ai/v2/{Config.RUNPOD_ENDPOINT_ID}/run"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {Config.RUNPOD_API_KEY}"
    }
    
    payload = {
        "input": {
            "audio_file": audio_b64,
            "stems": stems
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        job_id = result.get("id")
        
        if not job_id:
            raise ValueError("No job ID returned from RunPod API")
            
        logger.info(f"Submitted job to RunPod with ID: {job_id}")
        return job_id
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error submitting to RunPod: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error submitting to RunPod: {e}")
        raise


def check_runpod_status(job_id):
    """
    Check the status of a RunPod separation job.
    
    Args:
        job_id (str): Job ID returned from submit_to_runpod
        
    Returns:
        dict: Status information including completion status and results
    """
    if not Config.RUNPOD_API_KEY:
        raise ValueError("RUNPOD_API_KEY not configured")
    
    url = f"https://api.runpod.ai/v2/{Config.RUNPOD_ENDPOINT_ID}/status/{job_id}"
    
    headers = {
        "Authorization": f"Bearer {Config.RUNPOD_API_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking RunPod status: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error checking RunPod status: {e}")
        raise


def download_stem_from_url(stem_url, output_path):
    """
    Download a stem file from URL to local path.
    
    Args:
        stem_url (str): URL of the stem file
        output_path (str): Local path to save the stem file
        
    Returns:
        str: Path to the downloaded file
    """
    try:
        response = requests.get(stem_url)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
            
        logger.info(f"Downloaded stem from {stem_url} to {output_path}")
        return output_path
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading stem from {stem_url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading stem: {e}")
        raise


def separate_with_runpod(in_path, out_path, stems=None, max_wait_time=300):
    """
    Separate stems using RunPod API and download results to local directory.
    
    Args:
        in_path (str): Path to input audio file
        out_path (str): Path to output directory for stems
        stems (list): List of stems to separate (default: all available)
        max_wait_time (int): Maximum time to wait for completion in seconds
        
    Returns:
        dict: Information about the separated stems
        
    Raises:
        ValueError: If RunPod API key is not configured
        Exception: If RunPod separation fails or times out
    """
    if not Config.RUNPOD_API_KEY:
        raise ValueError("RunPod API key not configured. Please set RUNPOD_API_KEY environment variable.")
    
    if stems is None:
        stems = ["vocals", "drums", "bass", "guitar", "piano", "other"]
    
    os.makedirs(out_path, exist_ok=True)
    
    # Encode audio file to base64
    logger.info(f"Encoding audio file: {in_path}")
    audio_b64 = encode_audio_to_base64(in_path)
    
    # Submit job to RunPod
    logger.info("Submitting separation job to RunPod")
    job_id = submit_to_runpod(audio_b64, stems)
    
    # Poll for completion
    logger.info(f"Waiting for RunPod job {job_id} to complete...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        status_result = check_runpod_status(job_id)
        status = status_result.get("status")
        
        if status == "COMPLETED":
            logger.info("RunPod job completed successfully")
            output = status_result.get("output", {})
            stem_urls = output.get("stem_urls", {})
            available_stems = output.get("available_stems", [])
            
            # Download all available stems
            downloaded_stems = {}
            for stem_name in available_stems:
                if stem_name in stem_urls:
                    stem_url = stem_urls[stem_name]
                    output_file = os.path.join(out_path, f"{stem_name}.wav")
                    download_stem_from_url(stem_url, output_file)
                    downloaded_stems[stem_name] = output_file
            
            logger.info(f"Downloaded {len(downloaded_stems)} stems to {out_path}")
            return {
                "status": "completed",
                "stems": downloaded_stems,
                "available_stems": available_stems,
                "stem_urls": stem_urls
            }
            
        elif status == "FAILED":
            error_msg = status_result.get("error", "Unknown error")
            logger.error(f"RunPod job failed: {error_msg}")
            raise Exception(f"RunPod separation failed: {error_msg}")
            
        elif status in ["IN_QUEUE", "IN_PROGRESS"]:
            logger.info(f"Job status: {status}, waiting...")
            time.sleep(5)  # Wait 5 seconds before checking again
        else:
            logger.warning(f"Unknown job status: {status}")
            time.sleep(5)
    
    # Timeout
    raise Exception(f"RunPod job timed out after {max_wait_time} seconds")


def create_song_entry(title=None, artist=None, user_id=None, image_url=None, release_date=None):
    # Create the song entry dictionary
    song_entry = {
        "title": title,
        "artist": artist,
        "user_id": user_id,
        "image_url": image_url,
        "release_date": release_date,
        "tracks": []  # Initially empty, will be populated later
    }

    try:
        # Insert the song entry into the 'songs' table
        response = supabase.table("song").insert(song_entry).execute()
        return response.data[0]
    except Exception as e:
        logger.error("An error occurred while creating the song entry: %s", e)
        raise

def upload_song_to_storage(user_id, song_id, file_path, track_name):
    bucket_name = "yoke-stems"
    destination_path = f"{user_id}/{song_id}/{track_name}.wav"

    try:
        with open(file_path, "rb") as file:
            supabase.storage.from_(bucket_name).upload(destination_path, file)

        public_url = supabase.storage.from_(bucket_name).get_public_url(destination_path)
        return public_url
    except Exception as e:
        logger.error("An error occurred while uploading the file to Supabase: %s", e)
        raise


def recognize_song(file_path):
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                "https://api.audd.io/",
                data={
                    "api_token": Config.AUDD_API_KEY,
                    "return": "spotify"
                },
                files={
                    "file": f
                }
            )

        if response.status_code == 200:
            data = response.json()
            return data
        else:
            logger.error(f"Error recognizing song: {response.text}")
            raise ValueError("Error recognizing song.")
    except Exception as e:
        logger.error(f"Error recognizing song: {e}")
        raise


def combine_stems(stem_paths, output_path):
    """Deprecated: use mix_and_zip_stems for pydub-based mixing."""
    raise NotImplementedError("combine_stems is removed; use mix_and_zip_stems instead")


def process_audio_files(stem_paths, combined_audio_path):
    """Deprecated: use mix_and_zip_stems for pydub-based mixing."""
    raise NotImplementedError("process_audio_files is removed; use mix_and_zip_stems instead")


def cleanup_temp_files(*paths):
    """Delete temporary files and directories."""
    for path in paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)


def convert_audio(input_file, output_file, file_type):
    """
    Converts an audio file to the specified format using pydub.

    Parameters:
    - input_file (str): Path to the input audio file.
    - output_file (str): Path to the output audio file.
    - file_type (str): Target file type ('wav', 'mp3', 'ogg').
    """
    try:
        # Load the input audio file
        audio = AudioSegment.from_file(input_file)

        # Export the file in the desired format
        if file_type == "ogg":
            audio.export(output_file, format="ogg", codec="libopus", parameters=["-b:a", "128k"])
        else:
            audio.export(output_file, format=file_type)
        
        print(f"Converted {input_file} to {output_file} as {file_type}")
    except Exception as e:
        print(f"Error converting {input_file} to {file_type}: {e}")
        raise


def download_stems_zip(stem_names, file_type, session_id, output_path):
    """
    Creates a ZIP of selected stems in a single specified format from local temporary files.

    Parameters:
    - stem_names (list): List of stem names to include (e.g., ['vocals', 'guitar']).
    - file_type (str): Target file type for the download ('wav', 'mp3', or 'ogg').
    - session_id (str): Session ID for naming the ZIP file.
    - output_path (str): Path to the directory containing the stem files.

    Returns:
    - path to the ZIP file.
    """

    # Temp directory for processing
    temp_dir = tempfile.mkdtemp()
    zip_file_path = os.path.join(temp_dir, f"{session_id}_stems.zip")

    # Create a ZIP file
    with zipfile.ZipFile(zip_file_path, "w") as zipf:
        for stem in stem_names:
            input_file_name = f"{stem}.wav"  # Original files are WAV
            input_file_path = os.path.join(output_path, input_file_name)

            if os.path.exists(input_file_path):
                try:
                    # Convert to the desired format
                    output_file_name = f"{stem}.{file_type}"
                    output_file_path = os.path.join(temp_dir, output_file_name)
                    convert_audio(input_file_path, output_file_path, file_type)

                    # Add to ZIP
                    zipf.write(output_file_path, arcname=output_file_name)

                    # Clean up individual files
                    os.remove(output_file_path)
                except Exception as e:
                    logger.error(f"Could not process {stem}: {e}")
            else:
                logger.warning(f"Stem file not found: {input_file_path}")

    # Return path to the ZIP file
    return zip_file_path


def mix_and_zip_stems(stem_names, session_id, output_format="mp3", output_path=None):
    """
    Mixes the provided stems into a single audio file and returns a ZIP file path.

    Parameters:
    - stem_names (list): List of stem names to mix (e.g., ['vocals', 'guitar']).
    - session_id (str): Session ID for naming the output file.
    - output_format (str): The format of the mixed-down audio file ('mp3', 'wav', etc.).
    - output_path (str): Path to the directory containing the stem files.

    Returns:
    - str: Path to the ZIP file containing the mixed-down audio.
    """

    # Temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    mixed_file_name = f"{session_id}_mixdown.{output_format}"
    mixed_file_path = os.path.join(temp_dir, mixed_file_name)

    try:
        # Load and mix stems
        mixed_audio = None
        for stem in stem_names:
            file_name = f"{stem}.wav"  # Original files are WAV
            stem_path = os.path.join(output_path, file_name)

            if os.path.exists(stem_path):
                # Load the stem audio
                stem_audio = AudioSegment.from_file(stem_path)

                # Mix with the existing audio
                if mixed_audio is None:
                    mixed_audio = stem_audio
                else:
                    mixed_audio = mixed_audio.overlay(stem_audio)
            else:
                logger.warning(f"Stem file not found: {stem_path}")

        # Export the mixed-down audio
        if mixed_audio is not None:
            mixed_audio.export(mixed_file_path, format=output_format)
        else:
            raise ValueError("No stems found to mix.")

        # Create a ZIP file containing the mixdown
        zip_file_path = os.path.join(temp_dir, f"{session_id}_mixdown.zip")
        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            zipf.write(mixed_file_path, arcname=mixed_file_name)

        return zip_file_path

    except Exception as e:
        logger.error(f"Error mixing stems: {e}")
        raise
    finally:
        # Cleanup temporary files except the ZIP
        if os.path.exists(mixed_file_path):
            os.remove(mixed_file_path)


def _parse_created_at(value):
    """
    Best-effort parse of created_at values stored in session metadata.
    Supports ISO timestamps. Returns datetime in UTC or None.
    """
    if not value:
        return None
    try:
        # Expect ISO 8601
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _delete_supabase_objects_for_session(session_metadata):
    """
    Remove Supabase storage objects for a session if stem_urls are present.
    Falls back to deleting by known prefix pattern using session_id if needed.
    """
    try:
        stem_urls = session_metadata.get("stem_urls") or {}
        objects_to_remove = []

        # Fast path: remove each object from stem_urls
        for _, url in stem_urls.items():
            # URL format: https://<proj>.supabase.co/storage/v1/object/public/<bucket>/<path>
            parts = url.split('/storage/v1/object/public/')
            if len(parts) == 2:
                bucket_and_path = parts[1]
                first_slash = bucket_and_path.find('/')
                if first_slash != -1:
                    bucket = bucket_and_path[:first_slash]
                    path = bucket_and_path[first_slash + 1:]
                    if bucket and path:
                        objects_to_remove.append((bucket, path))

        # Remove collected objects grouped by bucket
        by_bucket = {}
        for bucket, path in objects_to_remove:
            by_bucket.setdefault(bucket, []).append(path)

        for bucket, paths in by_bucket.items():
            try:
                supabase.storage.from_(bucket).remove(paths)
            except Exception:
                pass

        # If no explicit URLs, try deleting by session_id prefix if known
        if not objects_to_remove:
            session_id = session_metadata.get("session_id")
            if session_id:
                # Common path pattern seen in URLs: stems/ff7e.../<stem>.wav
                # Adjust BUCKET name if needed via Config.SUPABASE_BUCKET
                bucket = Config.SUPABASE_BUCKET
                try:
                    # List and delete all with that prefix
                    listing = supabase.storage.from_(bucket).list(
                        path=f"{session_id}",
                        search=None
                    )
                    delete_paths = [f"{session_id}/{item.get('name')}" for item in listing or [] if item.get('name')]
                    if delete_paths:
                        supabase.storage.from_(bucket).remove(delete_paths)
                except Exception:
                    pass
    except Exception:
        # Never fail cleanup on storage errors
        pass


def cleanup_expired_sessions(max_age_hours: int = 24):
    """
    Delete local temp session directories and Supabase objects older than max_age_hours.
    Safe to run periodically.
    """
    try:
        temp_base = tempfile.gettempdir()
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(hours=max_age_hours)

        # Find all output_ session dirs
        for name in os.listdir(temp_base):
            if not name.startswith('output_'):
                continue
            session_dir = os.path.join(temp_base, name)
            if not os.path.isdir(session_dir):
                continue

            metadata_file = os.path.join(session_dir, 'session_metadata.json')
            created_at_dt = None
            session_metadata = {}

            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, 'r') as f:
                        session_metadata = json.load(f)
                    created_at_dt = _parse_created_at(session_metadata.get('created_at'))
                except Exception:
                    created_at_dt = None

            # If we have a timestamp, prefer it; else use folder mtime
            if created_at_dt is None:
                try:
                    mtime = os.path.getmtime(session_dir)
                    created_at_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                except Exception:
                    continue

            if created_at_dt <= cutoff:
                # Attempt to delete remote objects first
                _delete_supabase_objects_for_session(session_metadata)
                # Remove local directory
                try:
                    shutil.rmtree(session_dir)
                except Exception:
                    pass
    except Exception:
        # Never raise from background cleanup
        pass


def youtube_to_audio(youtube_url, output_file):
    """
    Download a YouTube video and convert it to a WAV audio file.

    Args:
        youtube_url (str): The URL of the YouTube video.
        output_file (str): The output WAV file path.

    Returns:
        str: Path to the downloaded WAV audio file.
    """
    try:
        # Ensure the output file always ends with `.wav`
        if not output_file.endswith(".wav"):
            output_file += ".wav"

        # Define yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',  # Best audio quality available
            'outtmpl': output_file.replace('.wav', ''),  # Temporary file without .wav
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',  # Extract WAV instead of MP3
                    'preferredquality': '0',  # Best quality (not applicable to WAV but kept for compatibility)
                }
            ],
            'postprocessor_args': [
                '-vn',  # Remove video stream
            ],
            'noplaylist': True,  # Do not download playlists
            'quiet': False,      # Display progress and information
        }

        # Download and process with yt-dlp
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        # Ensure the final output file exists
        if not os.path.exists(output_file):
            raise FileNotFoundError(f"Output file not found: {output_file}")

        return output_file
    except Exception as e:
        raise Exception(f"Error downloading or processing YouTube audio: {e}")