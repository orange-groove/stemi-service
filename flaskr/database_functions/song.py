import os

from flaskr.supabase_client import supabase
from flaskr.utils.helpers import (
    upload_song_to_storage
)

def create_song(song):
    """Create a song in the database.

    Args:
        song_name (str): The name of the song.
        artist_name (str): The name of the artist.
        album_name (str): The name of the album.
        song_url (str): The URL of the song.
        playlist_id (int): The ID of the playlist.

    Returns:
        dict: The song object.
    """
    song = supabase.table('songs').insert(song).execute()
    return song.data[0]

def get_playlist_songs(playlist_id):
    """Fetch all songs for a playlist.

    Args:
        playlist_id (int): The ID of the playlist.

    Returns:
        list: A list of song objects.
    """
    response = supabase.table('songs').select('*').eq('playlist_id', playlist_id).execute()

    return response.data

def get_user_songs(user_id):
    """Fetch all songs for a user.

    Args:
        user_id (int): The ID of the user.

    Returns:
        list: A list of song objects.
    """
    response = supabase.table('songs').select('*').eq('user_id', user_id).execute()
    return response.data



def update_song(song_id, song):
    """Update a song in the database.

    Args:
        song_id (int): The ID of the song.
        song (dict): The updated song object.

    Returns:
        dict: The updated song object.
    """
    song = supabase.table('songs').update(song).eq('id', song_id).execute()
    return song.data[0]


def delete_song(user_id, song_id):
    """
    Delete a song and its associated folder from Supabase.

    Args:
        song_id (int): The ID of the song.

    Returns:
        dict: The deleted song object or an error message if the deletion fails.
    """
    try:
        # Fetch the song details first to get playlist_id
        song_response = supabase.table('songs').select('*').eq('id', song_id).execute()
        if not song_response.data:
            raise ValueError(f"Song with ID {song_id} not found.")
        
        bucket_name = "yoke-stems"


        # Construct the folder path
        folder_path = f"{user_id}/{song_id}/"
        print(f"Deleting folder from bucket: {folder_path}")  # Debug log

        # List all files in the folder
        files = supabase.storage.from_(bucket_name).list(folder_path)
        if not isinstance(files, list):
            raise ValueError(f"Failed to list files in folder: {folder_path}")

        if not files:
            print(f"No files found in folder: {folder_path}")
        else:
            # Collect all file paths to delete
            file_paths = [f"{folder_path}{file['name']}" for file in files]
            print(f"File paths to delete: {file_paths}")  # Debug log

            # Delete all files in the folder
            delete_response = supabase.storage.from_(bucket_name).remove(file_paths)
            print(f"Delete response: {delete_response}")  # Debug log

            if delete_response:
                print(f"Deleted files: {file_paths}")
            else:
                raise ValueError(f"Failed to delete some files in folder: {folder_path}")

        # Supabase automatically removes folders when they're empty

        # Delete playlists_songs records associated with the song
        delete_playlist_songs_response = supabase.table('playlists_songs').delete().eq('song_id', song_id).execute()
        
        if delete_playlist_songs_response is None:
            raise ValueError(f"Failed to delete playlist_songs records for song ID {song_id}.")

        # Delete the song record from the database
        delete_response = supabase.table('songs').delete().eq('id', song_id).execute()
        if not delete_response.data:
            raise ValueError(f"Failed to delete song record with ID {song_id}.")

        print(f"Successfully deleted song ID {song_id} and its folder.")
        return delete_response.data[0]

    except Exception as e:
        print(f"Error deleting song: {e}")
        return {"error": str(e)}


def get_song(song_id):
    """Fetch a song by its ID.

    Args:
        song_id (int): The ID of the song.

    Returns:
        dict: The song object.
    """
    response = supabase.table('songs').select('*').eq('id', song_id).execute()

    # Handle the response based on its structure
    if not response.data:  # Check if data exists
        raise ValueError("No song found with this ID.")

    return response.data[0]

def update_song(song_id, song):
    """Update a song in the database.

    Args:
        song_id (int): The ID of the song.
        song (dict): The updated song object.

    Returns:
        dict: The updated song object.
    """

    response = supabase.table('songs').update(song).eq('id', song_id).execute()

    return response.data[0]


def upload_song_stems_and_update_db(song_entry, output_path, stem_names):
    song_id = song_entry['id']
    user_id = song_entry['user_id']
    tracks = []

    try:
        for stem_name in stem_names:
            file_path = os.path.join(output_path, f"{stem_name}.wav")
            url = upload_song_to_storage(user_id, song_id, file_path, stem_name)
            tracks.append({"name": stem_name, "url": url})

        # Update the song entry with the track URLs
        response = supabase.table("songs").update({
            "tracks": tracks, 
            "title": song_entry['title'],
            "artist": song_entry['artist'],
            "image_url": song_entry['image_url'],
            "tempo_changes": song_entry['tempo_changes'],
            "song_key": song_entry['song_key'],
        }).eq("id", song_id).execute()

        return response.data[0]
    
    except Exception as e:
        print(f"Error uploading song stems: {e}")
        return {"error": str(e)}

