import os
import shutil
import demucs.separate
from flaskr.supabase_client import supabase
import logging

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

def create_song_entry(name, description, user_id):
    # Create the song entry dictionary
    song_entry = {
        "name": name,
        "description": description,
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
    
def upload_song_stems_and_update_db(song_entry, output_path, stem_names):
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
            response = supabase.table("song").update({"tracks": tracks}).eq("id", song_id).execute()
            
            return response.data[0]
        
        except Exception as e:
            print(f"Error updating song entry with tracks: {e}")
            raise e