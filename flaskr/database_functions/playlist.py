from flaskr.supabase_client import supabase


def create_playlist(playlist):
    """Create a playlist in the database.

    Args:
        playlist (dict): The playlist data.

    Returns:
        dict: The created playlist.
    """
    try:
        response = supabase.table('playlists').insert(playlist).execute()

        if not response.data:
            raise RuntimeError("Failed to create playlist: No data returned.")

        return response.data[0]
    except Exception as e:
        raise RuntimeError(f"Error creating playlist: {e}")


def get_playlists(user_id):
    """
    Fetch all playlists for a specific user with their songs included.

    Args:

    Returns:
        list: A list of playlists with nested songs.
    """
    try:
        if not user_id:
            raise ValueError("User ID is required.")

        # Use Supabase query to fetch playlists with nested songs
        response = supabase.table('playlists').select("*").eq('user_id', user_id).execute()

        if response.data is None:
            raise RuntimeError("Failed to fetch playlists: No data returned.")
        
        if not response.data:
            return []  # Return an empty list if no playlists are found.

        return response.data
    except Exception as e:
        raise RuntimeError(f"Error fetching playlists with songs for user {user_id}: {e}")


def get_playlist(playlist_id):
    """Fetch a playlist by ID.

    Args:
        playlist_id (str): The ID of the playlist.

    Returns:
        dict: The playlist object.
    """
    try:
        if not playlist_id or not isinstance(playlist_id, str):
            raise ValueError("Valid playlist ID is required.")

        response = supabase.table('playlists').select("*, songs(id, title, artist, image_url, playlist_id, created_at)").eq('id', playlist_id).execute()

        if response.data is None:
            raise RuntimeError("Failed to fetch playlist: No data returned.")

        if not response.data:
            raise ValueError(f"No playlist found with ID {playlist_id}.")

        return response.data[0]
    except Exception as e:
        raise RuntimeError(f"Error fetching playlist with ID {playlist_id}: {e}")
    

def update_playlist(playlist_id, playlist):
    """Update a playlist in the database.

    Args:
        playlist_id (str): The ID of the playlist to update.
        playlist (dict): The updated playlist data.

    Returns:
        dict: The updated playlist.
    """
    try:
        if not playlist_id or not isinstance(playlist_id, str):
            raise ValueError("Valid playlist ID is required.")
        
        if not isinstance(playlist, dict) or 'title' not in playlist:
            raise ValueError("Playlist data must include 'title'.")

        response = supabase.table('playlists').update(playlist).eq('id', playlist_id).execute()

        if response.data is None:
            raise RuntimeError("Failed to update playlist: No data returned.")

        if not response.data:
            raise ValueError(f"No playlist found with ID {playlist_id}.")

        return response.data[0]
    except Exception as e:
        raise RuntimeError(f"Error updating playlist with ID {playlist_id}: {e}")


def delete_playlist(playlist_id):
    """
    Delete a playlist, its associated bucket files, and its database record from Supabase.

    Args:
        playlist_id (int or str): The ID of the playlist to delete.

    Returns:
        dict: The deleted playlist object or an error message if the deletion fails.
    """
    try:
        bucket_name = "yoke-stems"
        playlist_id_str = str(playlist_id)

        # List all song folders under the playlist directory
        folder_path = f"{playlist_id_str}/"
        print(f"Listing folders in bucket under: {folder_path}")
        folders = supabase.storage.from_(bucket_name).list(folder_path)

        if folders is None:
            raise ValueError(f"Failed to list folders in playlist directory: {folder_path}")

        for folder in folders:
            song_folder_path = f"{folder_path}{folder['name']}/"
            print(f"Processing folder: {song_folder_path}")

            # List all files in the song folder
            files = supabase.storage.from_(bucket_name).list(song_folder_path)
            if files is None:
                raise ValueError(f"Failed to list files in folder: {song_folder_path}")

            if not files:
                print(f"No files found in folder: {song_folder_path}")
            else:
                # Collect all file paths to delete
                file_paths = [f"{song_folder_path}{file['name']}" for file in files]
                print(f"File paths to delete: {file_paths}")

                # Delete all files in the folder
                delete_response = supabase.storage.from_(bucket_name).remove(file_paths)
                print(f"Delete response for folder {song_folder_path}: {delete_response}")

                if delete_response is None:
                    raise ValueError(f"Failed to delete files in folder: {song_folder_path}")
                else:
                    print(f"Deleted files in folder {song_folder_path}")

        # Delete the songs associated with the playlist from the database
        delete_songs_response = supabase.table('songs').delete().eq('playlist_id', playlist_id).execute()
        if delete_songs_response is None or not delete_songs_response.data:
            print(f"No songs found for playlist ID {playlist_id}, skipping song deletion.")

        # Delete the playlist record
        delete_playlist_response = supabase.table('playlists').delete().eq('id', playlist_id).execute()
        if delete_playlist_response is None or not delete_playlist_response.data:
            raise ValueError(f"Failed to delete playlist with ID {playlist_id}.")

        print(f"Successfully deleted playlist ID {playlist_id}.")
        return delete_playlist_response.data[0]

    except Exception as e:
        print(f"Error deleting playlist: {e}")
        return {"error": str(e)}


def get_playlist_songs(playlist_id):
    """Fetch all songs for a playlist.

    Args:
        playlist_id (str): The ID of the playlist.

    Returns:
        list: A list of songs in the playlist.
    """
    try:
        if not playlist_id or not isinstance(playlist_id, str):
            raise ValueError("Valid playlist ID is required.")

        response = supabase.table('songs').select('*').eq('playlist_id', playlist_id).execute()

        if response.data is None:
            raise RuntimeError("Failed to fetch songs: No data returned.")

        if not response.data:
            return []  # Return an empty list if no songs are found.

        return response.data
    except Exception as e:
        raise RuntimeError(f"Error fetching songs for playlist with ID {playlist_id}: {e}")
