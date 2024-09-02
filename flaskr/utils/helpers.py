import os
import shutil
import demucs.separate
from flaskr.supabase_client import supabase
import logging
import librosa
import numpy as np
import soundfile as sf
from openai import OpenAI
client = OpenAI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def separate(in_path, out_path, algorithm):
    in_path = os.path.abspath(in_path)  # Ensure absolute path
    out_path = os.path.abspath(out_path)  # Ensure absolute path

    # Ensure the output directory exists
    os.makedirs(out_path, exist_ok=True)

    # Temporary directory for Demucs output
    temp_output_dir = os.path.join(out_path, algorithm)
    os.makedirs(temp_output_dir, exist_ok=True)

    # Run the separation
    print(f"Running Demucs separation on {in_path} with temporary output directory {temp_output_dir}")
    try:
        demucs.separate.main([
            "--mp3",  # Save output as MP3
            "--two-stems", None,  # Separate into vocals and no_vocals
            "-n", algorithm,  # Use the htdemucs model by default
            str(in_path),  # Input path
            "-o", temp_output_dir,  # Output to the temporary directory
            "-j", "4"
        ])
    except Exception as e:
        print(f"Error running Demucs: {e}")

    # Move the separated files to the final output directory
    for root, dirs, files in os.walk(temp_output_dir):
        for file in files:
            shutil.move(os.path.join(root, file), os.path.join(out_path, file))

    # Clean up the temporary directory
    shutil.rmtree(temp_output_dir)

    # Check if the output directory has files
    if not os.listdir(out_path):
        raise RuntimeError(f"Demucs did not generate any files in {out_path}.")
    else:
        print(f"Demucs separation completed successfully. Output files: {os.listdir(out_path)}")

def create_song_entry(name, artist, user_id):
    # Create the song entry dictionary
    song_entry = {
        "name": name,
        "artist": artist,
        "user_id": user_id,
        "tracks": []  # Initially empty, will be populated later
    }
    
    try:
        # Attempt to insert the song entry into the 'songs' table
        response = supabase.table("song").insert(song_entry).execute()

        print('response', response)
        # Return the created song entry
        return response.data[0]
    
    except Exception as e:
        # Handle exceptions and provide useful error messages
        logger.error("An error occurred while creating the song entry: %s", e)
        raise e

def upload_to_supabase(user_id, song_id, file_path, track_name):
    # Define the bucket and path
    bucket_name = "yoke-stems"
    destination_path = f"{user_id}/{song_id}/{track_name}.mp3"

    try:
        # Upload the file to Supabase storage
        with open(file_path, "rb") as file:
            supabase.storage.from_(bucket_name).upload(destination_path, file)

        # Return the public URL of the uploaded file
        public_url = supabase.storage.from_(bucket_name).get_public_url(destination_path)
        return public_url
    
    except Exception as e:
        # Handle exceptions and provide useful error messages
        logger.error("An error occurred while uploading the file to Supabase: %s", e)
        raise e
    
def upload_song_stems_and_update_db(song_entry, output_path, stem_names, key_changes, tempo_changes):
        user_id = song_entry['user_id']
        song_id = song_entry['id']
        tracks = []
        
        try:
            for stem_name in stem_names:
                file_path = os.path.join(output_path, f"{stem_name}.mp3")
                url = upload_to_supabase(user_id, song_id, file_path, stem_name)
                
                # Add track info to the list
                tracks.append({
                    "name": stem_name,
                    "url": url
                })
            
            # Update the song entry with the track URLs
            response = supabase.table("song").update({
                "tracks": tracks, 
                "key_changes": key_changes, 
                "tempo_changes": tempo_changes
            }).eq("id", song_id).execute()
            
            return response.data[0]
        
        except Exception as e:
            print(f"Error updating song entry with tracks: {e}")
            raise e


def analyze_audio(file_path):
    # Load the audio file
    y, sr = librosa.load(file_path, sr=None)
    
    # Check if audio file is loaded correctly
    if np.all(y == 0):
        raise ValueError("Audio file is silent or corrupted.")
    
    # Beat tracking to find beats and tempo
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    print(f"Tempo: {tempo}")
    print(f"Beats: {beats}")
    
    # Harmonic component extraction
    harmonic, _ = librosa.effects.hpss(y)
    
    # Debugging: Check harmonic signal
    if np.all(harmonic == 0):
        raise ValueError("Harmonic component is silent.")
    print(f"Harmonic signal shape: {harmonic.shape}")
    
    # Chroma feature extraction
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sr)
    
    # Debugging: Check chroma features
    print(f"Chroma feature shape: {chroma.shape}")
    print(f"Chroma feature sample: {chroma[:, :10]}")

    # Mapping chroma index to musical notes
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    def detect_key(chroma_slice):
        key_index = np.argmax(np.sum(chroma_slice, axis=1))
        return note_names[key_index % 12]

    
    keys_per_beat = []
    tempo_changes = []

    previous_tempo = tempo
    tempo_changes.append({'beat': 0, 'tempo': float(previous_tempo)})

    for i in range(len(beats) - 1):
        start = int(beats[i])
        end = int(beats[i + 1])

        if end > len(y):
            end = len(y)

        chroma_slice = chroma[:, start:end]
        key = detect_key(chroma_slice)
        keys_per_beat.append(key)

        current_tempo, _ = librosa.beat.beat_track(y=y[start:end], sr=sr)
        if np.abs(current_tempo - previous_tempo) > 1:
            tempo_changes.append({'beat': i + 1, 'tempo': float(current_tempo)})
            previous_tempo = current_tempo

    key_changes = []
    previous_key = None

    for beat, key in enumerate(keys_per_beat):
        if key != previous_key:
            key_changes.append({'beat': beat, 'key': key})
            previous_key = key

    if len(tempo_changes) == 1 and tempo_changes[0]['beat'] == 0:
        tempo_changes.append({'beat': len(beats), 'tempo': float(previous_tempo)})

    result = {
        'key_changes': key_changes,
        'tempo_changes': tempo_changes
    }

    return result

def get_song_info(artist_name, song_name):
    # Define the roles and initial message
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides detailed information about songs and artists."},
        {"role": "user", "content": f"Please provide information about the song '{song_name}' by the artist '{artist_name}'."}
    ]

    # Make the chat request
    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        max_tokens=150,  # You can adjust the max_tokens depending on how much detail you want
        temperature=0.7  # Adjust the creativity of the response
    )

    # Extract the content from the response
    song_info = completion.choices[0].message.model_dump_json()
    return song_info

def combine_stems(stem_paths, output_path):
    combined_audio_data = None
    for stem_path in stem_paths:
        y, sr = librosa.load(stem_path, sr=None)
        if combined_audio_data is None:
            combined_audio_data = y
        else:
            combined_audio_data += y
    if combined_audio_data is not None:
        combined_audio_data /= len(stem_paths)  # Normalize by the number of stems
        sf.write(output_path, combined_audio_data, sr)