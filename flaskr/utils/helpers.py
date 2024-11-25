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
import subprocess

# Initialize OpenAI client
client = OpenAI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

logger = logging.getLogger(__name__)

def convert_to_ogg(input_path, output_path):
    """
    Converts a WAV file to OGG format using FFmpeg.
    """
    try:
        subprocess.run([
            "ffmpeg",
            "-i", input_path,
            "-c:a", "libopus",  # Use Opus encoder
            "-b:a", "96k",      # Set bitrate (adjust for quality vs. size)
            output_path
        ], check=True)
        logger.info(f"Converted {input_path} to {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error converting to OGG: {e}")
        raise

def separate(in_path, out_path, algorithm):
    in_path = os.path.abspath(in_path)  # Ensure absolute path
    out_path = os.path.abspath(out_path)  # Ensure absolute path

    # Ensure the output directory exists
    os.makedirs(out_path, exist_ok=True)

    # Temporary directory for Demucs WAV output
    temp_output_dir = os.path.join(out_path, algorithm)
    os.makedirs(temp_output_dir, exist_ok=True)

    # Run the separation
    logger.info(f"Running Demucs separation on {in_path} with temporary output directory {temp_output_dir}")
    try:
        demucs.separate.main([
            "--two-stems", None,  # Separate into vocals and no_vocals
            "-n", algorithm,      # Use the specified model
            str(in_path),         # Input path
            "-o", temp_output_dir,  # Output to the temporary directory
        ])
    except Exception as e:
        logger.error(f"Error running Demucs: {e}")
        raise

    # Convert WAV files to OGG and move to final output directory
    for root, _, files in os.walk(temp_output_dir):
        for file in files:
            if file.endswith(".wav"):
                input_wav = os.path.join(root, file)
                output_ogg = os.path.join(out_path, os.path.splitext(file)[0] + ".ogg")
                convert_to_ogg(input_wav, output_ogg)

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

def upload_song_to_storage(playlist_id, song_id, file_path, track_name):
    bucket_name = "yoke-stems"
    destination_path = f"{playlist_id}/{song_id}/{track_name}.ogg"

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


# def analyze_audio(file_path):
#     try:
#         y, sr = librosa.load(file_path, sr=None)
#         if np.all(y == 0):
#             raise ValueError("Audio file is silent or corrupted.")

#         # Determine an appropriate n_fft value based on the signal length
#         # n_fft = min(2048, len(y))  # Use 2048 or the length of the signal, whichever is smaller

#         tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
#         logger.info(f"Tempo: {tempo}, Beats: {beats}")

#         harmonic, _ = librosa.effects.hpss(y)
#         if np.all(harmonic == 0):
#             raise ValueError("Harmonic component is silent.")

#         hop_length = min(512, len(y) // 10)
#         # Use the dynamically determined n_fft value
#         chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sr, hop_length=hop_length)

#         def detect_key(chroma_slice):
#             key_index = np.argmax(np.sum(chroma_slice, axis=1))
#             return note_names[key_index % 12]

#         keys_per_beat = []
#         tempo_changes = []

#         previous_tempo = tempo
#         tempo_changes.append({'beat': 0, 'tempo': float(previous_tempo)})

#         for i in range(len(beats) - 1):
#             start = int(beats[i])
#             end = min(int(beats[i + 1]), len(y))

#             if end - start > 0:  # Ensure the segment is valid
#                 chroma_slice = chroma[:, start:end]
#                 key = detect_key(chroma_slice)
#                 keys_per_beat.append(key)

#                 current_tempo, _ = librosa.beat.beat_track(y=y[start:end], sr=sr)
#                 if np.abs(current_tempo - previous_tempo) > 1:
#                     tempo_changes.append({'beat': i + 1, 'tempo': float(current_tempo)})
#                     previous_tempo = current_tempo

#         key_changes = []
#         previous_key = None

#         for beat, key in enumerate(keys_per_beat):
#             if key != previous_key:
#                 key_changes.append({'beat': beat, 'key': key})
#                 previous_key = key

#         if len(tempo_changes) == 1 and tempo_changes[0]['beat'] == 0:
#             tempo_changes.append({'beat': len(beats), 'tempo': float(previous_tempo)})

#         return {'key_changes': key_changes, 'tempo_changes': tempo_changes}

#     except Exception as e:
#         logger.error(f"Error analyzing audio: {e}")
#         raise


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