import os
import shutil
import demucs.separate
from flaskr.supabase_client import supabase
import logging
import librosa
import soundfile as sf
from openai import OpenAI
import json
from flaskr.config import Config
import requests
import tempfile
import zipfile
from pydub import AudioSegment
import numpy as np
from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)
# Initialize OpenAI client
client = OpenAI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

logger = logging.getLogger(__name__)

def separate(in_path, out_path):
    """
    Separates stems using Demucs and stores WAV files in the specified output directory.

    Parameters:
    - in_path: Path to the input audio file.
    - out_path: Path to the directory where output stems will be stored.
    - algorithm: The Demucs algorithm/model to use.
    """
    in_path = os.path.abspath(in_path)  # Ensure absolute path
    out_path = os.path.abspath(out_path)  # Ensure absolute path

    # Ensure the output directory exists
    os.makedirs(out_path, exist_ok=True)

    # Temporary directory for Demucs WAV output
    temp_output_dir = os.path.join(out_path, 'htdemucs_6s')
    os.makedirs(temp_output_dir, exist_ok=True)

    # Run the separation
    logger.info(f"Running Demucs separation on {in_path} with temporary output directory {temp_output_dir}")
    try:
        demucs.separate.main([
            "--two-stems", None,  # Separate into vocals and no_vocals
            "-n", 'htdemucs_6s',      # Use the specified model
            str(in_path),         # Input path
            "-o", temp_output_dir,  # Output to the temporary directory
        ])
    except Exception as e:
        logger.error(f"Error running Demucs: {e}")
        raise

    # Move WAV files to the final output directory
    for root, _, files in os.walk(temp_output_dir):
        for file in files:
            if file.endswith(".wav"):
                input_wav = os.path.join(root, file)
                output_wav = os.path.join(out_path, file)  # Keep the original WAV file name
                shutil.move(input_wav, output_wav)

    # Clean up the temporary directory
    shutil.rmtree(temp_output_dir)

    # Check if the output directory has files
    if not os.listdir(out_path):
        raise RuntimeError(f"Demucs did not generate any files in {out_path}.")
    else:
        logger.info(f"Demucs separation completed successfully. Output files: {os.listdir(out_path)}")


def create_song_entry(title=None, artist=None, user_id=None, playlist_id=None, image_url=None, release_date=None):
    # Create the song entry dictionary
    song_entry = {
        "title": title,
        "artist": artist,
        "user_id": user_id,
        "playlist_id": playlist_id,
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


def analyze_song(file_path):
    try:
        # Load the audio file
        y, sr = librosa.load(file_path, sr=None)
        if np.all(y == 0):
            raise ValueError("Audio file is silent or corrupted.")
        
        # Extract global tempo and beats
        global_tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        logger.info(f"Global Tempo: {global_tempo}, Beats: {len(beats)}")

        if len(beats) == 0:
            raise ValueError("No beats detected in the audio.")

        # Harmonic component for key detection
        harmonic, _ = librosa.effects.hpss(y)
        if np.all(harmonic == 0):
            raise ValueError("Harmonic component is silent.")

        # Key detection for the entire song (Major or Minor)
        chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sr)
        chroma_sum = np.sum(chroma, axis=1)
        key_index = np.argmax(chroma_sum)
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # Analyze relative major or minor key
        is_minor = np.sum(chroma_sum[[0, 2, 4, 5, 7, 9, 11]]) < np.sum(chroma_sum[[1, 3, 6, 8, 10]])
        overall_key = note_names[key_index % 12] + ('m' if is_minor else '')

        # Calculate tempo for a small window around each beat
        window_size = 2 * sr // 10  # 200ms window around each beat
        tempo_changes = []

        for beat_time in beats:
            start = max(0, int(beat_time * sr) - window_size // 2)
            end = min(len(y), start + window_size)
            segment = y[start:end]

            segment_tempo, _ = librosa.beat.beat_track(y=segment, sr=sr)
            if segment_tempo > 0:
                tempo_changes.append(float(segment_tempo))
            else:
                tempo_changes.append(float(global_tempo))  # Fallback to global tempo

        # Return the overall key and tempo changes
        return {'song_key': overall_key, 'tempo_changes': tempo_changes}

    except Exception as e:
        logger.error(f"Error analyzing audio: {e}")
        raise


def get_song_info(artist_name, song_name):
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides detailed information about songs and artists."},
        {"role": "user", "content": f"Please provide information about the song '{song_name}' by the artist '{artist_name}'."}
    ]

    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )

        # Parse the JSON string into a Python dictionary
        song_info = json.loads(completion.choices[0].message.model_dump_json())
        return song_info
    except Exception as e:
        logger.error(f"Error getting song info from OpenAI: {e}")
        raise


def get_popup_info(artist_name, song_name):
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides detailed information about songs and artists in the form of VH1 Pop up video."},
        {"role": "user", "content": f"Please provide information about the song '{song_name}' by the artist '{artist_name}'. Format the output as a JSON array of 3 strings containing fun facts about the song and artist."}
    ]

    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )

        # Parse the content into a JSON array
        popups = completion.choices[0].message.model_dump_json()
        popups_dict = json.loads(popups)

        # Ensure that the 'content' field is parsed as an array
        if 'content' in popups_dict:
            popups_dict['content'] = json.loads(popups_dict['content'])

        return popups_dict
    except Exception as e:
        logger.error(f"Error getting pop-up info from OpenAI: {e}")
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


def download_stems_zip(stem_names, file_type, song_id):
    """
    Downloads a ZIP of selected stems in a single specified format from Supabase storage.

    Parameters:
    - stem_names (list): List of stem names to include (e.g., ['vocals', 'guitar']).
    - file_type (str): Target file type for the download ('wav', 'mp3', or 'ogg').
    - playlist_id (str): Playlist ID to locate stems.
    - song_id (str): Song ID to locate stems.
    - supabase_url (str): Supabase project URL.
    - supabase_key (str): Supabase API key.

    Returns:
    - path to the ZIP file.
    """

    # Temp directory for downloaded files
    temp_dir = tempfile.mkdtemp()
    zip_file_path = os.path.join(temp_dir, f"{song_id}_stems.zip")

    # Create a ZIP file
    with zipfile.ZipFile(zip_file_path, "w") as zipf:
        for stem in stem_names:
            file_name = f"{stem}.wav"  # Assume original files are WAV
            supabase_path = f"{song_id}/{file_name}"

            # Download the file from Supabase
            try:
                response = supabase.storage.from_("yoke-stems").download(supabase_path)
                if response:
                    # Save the downloaded WAV file
                    wav_path = os.path.join(temp_dir, file_name)
                    with open(wav_path, "wb") as f:
                        f.write(response)

                    # Convert to the desired format
                    output_file_name = f"{stem}.{file_type}"
                    output_file_path = os.path.join(temp_dir, output_file_name)
                    convert_audio(wav_path, output_file_path, file_type)

                    # Add to ZIP
                    zipf.write(output_file_path, arcname=output_file_name)

                    # Clean up individual files
                    os.remove(wav_path)
                    os.remove(output_file_path)
            except Exception as e:
                print(f"Could not process {supabase_path}: {e}")

    # Return path to the ZIP file
    return zip_file_path


def mix_and_zip_stems(stem_names, song_id, output_format="mp3"):
    """
    Mixes the provided stems into a single audio file and returns a ZIP file path.

    Parameters:
    - stem_names (list): List of stem names to mix (e.g., ['vocals', 'guitar']).
    - song_id (str): Song ID to locate stems in the bucket.
    - output_format (str): The format of the mixed-down audio file ('mp3', 'wav', etc.).

    Returns:
    - str: Path to the ZIP file containing the mixed-down audio.
    """

    # Temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    mixed_file_name = f"{song_id}_mixdown.{output_format}"
    mixed_file_path = os.path.join(temp_dir, mixed_file_name)

    try:
        # Load and mix stems
        mixed_audio = None
        for stem in stem_names:
            file_name = f"{stem}.wav"  # Assume original files are WAV
            supabase_path = f"{song_id}/{file_name}"

            # Download the stem
            response = supabase.storage.from_("yoke-stems").download(supabase_path)
            if response:
                # Save the stem locally
                stem_path = os.path.join(temp_dir, file_name)
                with open(stem_path, "wb") as f:
                    f.write(response)

                # Load the stem audio
                stem_audio = AudioSegment.from_file(stem_path)

                # Mix with the existing audio
                if mixed_audio is None:
                    mixed_audio = stem_audio
                else:
                    mixed_audio = mixed_audio.overlay(stem_audio)

        # Export the mixed-down audio
        if mixed_audio is not None:
            mixed_audio.export(mixed_file_path, format=output_format)
        else:
            raise ValueError("No stems found to mix.")

        # Create a ZIP file containing the mixdown
        zip_file_path = os.path.join(temp_dir, f"{song_id}_mixdown.zip")
        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            zipf.write(mixed_file_path, arcname=mixed_file_name)

        return zip_file_path

    except Exception as e:
        print(f"Error mixing stems: {e}")
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