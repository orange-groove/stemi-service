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
                '-n', 'htdemucs',
                '-d', device,
                '-o', temp_demucs_dir,
                in_path
            ]
            
            # Run demucs
            demucs_main()
            
            # Find the output files
            import glob
            import shutil
            
            # Look for the demucs output directory
            demucs_output_dirs = glob.glob(os.path.join(temp_demucs_dir, 'htdemucs', '*'))
            if demucs_output_dirs:
                demucs_output_dir = demucs_output_dirs[0]
                
                # Copy the stem files to our output directory
                stem_files = glob.glob(os.path.join(demucs_output_dir, '*.wav'))
                stem_names = ['vocals', 'bass', 'drums', 'guitar', 'piano', 'other']
                
                for i, stem_file in enumerate(stem_files):
                    if i < len(stem_names):
                        stem_name = stem_names[i]
                        output_file = os.path.join(out_path, f"{stem_name}.wav")
                        shutil.copy2(stem_file, output_file)
                        logger.info(f"Copied {stem_file} to {output_file}")
                
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