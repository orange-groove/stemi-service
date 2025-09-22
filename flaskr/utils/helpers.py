import os
import shutil
import demucs.separate
from flaskr.supabase_client import supabase
import logging
import librosa
import soundfile as sf
# from openai import OpenAI
import json
from flaskr.config import Config
import requests
import tempfile
import zipfile
from pydub import AudioSegment
import numpy as np
from yt_dlp import YoutubeDL
import torch
import demucs
import base64
import time

logger = logging.getLogger(__name__)
# Initialize OpenAI client
# client = OpenAI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

logger = logging.getLogger(__name__)

def separate(in_path, out_path):
    """
    Separates stems using Demucs and stores WAV files in the specified output directory.
    Optimized for GPU acceleration and better resource management.
    """
    # Check if GPU is available
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Using device: {device}")
    
    in_path = os.path.abspath(in_path)
    out_path = os.path.abspath(out_path)
    os.makedirs(out_path, exist_ok=True)

    try:
        # Use the simpler demucs approach
        from demucs.separate import main as demucs_main
        import sys
        import tempfile
        
        # Create a temporary directory for demucs output
        temp_demucs_dir = tempfile.mkdtemp()
        
        # Save original sys.argv and replace with demucs arguments
        original_argv = sys.argv.copy()
        try:
            sys.argv = [
                'demucs.separate',
                '-n', 'htdemucs_6s',
                '-d', device,
                '-o', temp_demucs_dir,
                in_path
            ]
            
            # Run demucs
            demucs_main()
            
            # Find the output files
            import glob
            import shutil
            
            # Look for the demucs output directory - htdemucs_6s creates nested structure
            # First find the song directory inside htdemucs_6s
            song_dirs = glob.glob(os.path.join(temp_demucs_dir, 'htdemucs_6s', '*'))
            demucs_output_dirs = []
            
            for song_dir in song_dirs:
                if os.path.isdir(song_dir):
                    demucs_output_dirs.append(song_dir)
                    break
            
            if not demucs_output_dirs:
                # Fallback to other model patterns
                demucs_output_dirs = glob.glob(os.path.join(temp_demucs_dir, 'htdemucs', '*'))
            
            logger.info(f"Looking for demucs output in: {temp_demucs_dir}")
            logger.info(f"Found demucs output dirs: {demucs_output_dirs}")
            
            if demucs_output_dirs:
                demucs_output_dir = demucs_output_dirs[0]
                logger.info(f"Using demucs output dir: {demucs_output_dir}")
                
                # List all files in the demucs output directory
                all_files = os.listdir(demucs_output_dir)
                logger.info(f"All files in demucs output: {all_files}")
                
                # Copy the stem files to our output directory
                stem_files = glob.glob(os.path.join(demucs_output_dir, '*.wav'))
                logger.info(f"Found demucs output files: {stem_files}")
                
                stem_names = ['vocals', 'bass', 'drums', 'guitar', 'piano', 'other']
                
                for i, stem_file in enumerate(stem_files):
                    if i < len(stem_names):
                        stem_name = stem_names[i]
                        output_file = os.path.join(out_path, f"{stem_name}.wav")
                        shutil.copy2(stem_file, output_file)
                        logger.info(f"Copied {stem_file} to {output_file}")
                    else:
                        logger.warning(f"Extra stem file found: {stem_file}")
                
                # Check what files were actually created
                created_files = glob.glob(os.path.join(out_path, '*.wav'))
                logger.info(f"Final output files created: {created_files}")
                
                # Clean up
                shutil.rmtree(temp_demucs_dir)
            else:
                raise ValueError("No demucs output found")
                
        finally:
            # Restore original sys.argv
            sys.argv = original_argv
            
    except Exception as e:
        logger.error(f"Error during stem separation: {str(e)}")
        raise


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
    combined_audio_data = None
    sr = None
    for stem_path in stem_paths:
        y, sr = librosa.load(stem_path, sr=None)
        if combined_audio_data is None:
            combined_audio_data = y
        else:
            combined_audio_data += y

    if combined_audio_data is not None and sr is not None:
        combined_audio_data /= len(stem_paths)  # Normalize by the number of stems
        sf.write(output_path, combined_audio_data, sr)
    else:
        logger.error("No audio data to combine.")
        raise ValueError("No audio data to combine.")


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