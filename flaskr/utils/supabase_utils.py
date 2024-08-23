import time
from supabase import create_client
from flaskr.config import Config

# Initialize Supabase client
supabase_url = Config.SUPABASE_URL
supabase_key = Config.SUPABASE_KEY
supabase_bucket = Config.SUPABASE_BUCKET
supabase = create_client(supabase_url, supabase_key)


def create_user(email, password):
    """
    Register a new user in Supabase.
    
    Args:
        email (str): The user's email address.
        password (str): The user's password.
    
    Returns:
        dict: The response from Supabase containing user details or an error.
    """
    try:
        response = supabase.auth.sign_up({
            'email': email,
            'password': password,
        })
        if response.get("error"):
            raise Exception(response["error"]["message"])
        return response.get("user")
    except Exception as e:
        raise Exception(f"Error creating user: {str(e)}")

def sign_in_user(email, password):
    """
    Sign in an existing user with Supabase.
    
    Args:
        email (str): The user's email address.
        password (str): The user's password.
    
    Returns:
        dict: The response from Supabase containing user details or an error.
    """
    try:
        response = supabase.auth.sign_in({
            'email': email,
            'password': password,
        })
        if response.get("error"):
            raise Exception(response["error"]["message"])
        return response.get("user")
    except Exception as e:
        raise Exception(f"Error signing in user: {str(e)}")


def generate_directory_name(user_name):
    """Generate a unique directory name based on the user and timestamp."""
    timestamp = int(time.time())
    return f"{user_name}/song_{timestamp}"


def upload_to_supabase(file_path, storage_path):
    """Upload a file to Supabase Storage."""
    with open(file_path, "rb") as file:
        response = supabase.storage.from_(supabase_bucket).upload(storage_path, file.read())
    
    if response.status_code != 200:
        print(f"Error uploading file: {response.json()}")
        return None
    else:
        print(f"File uploaded successfully: {storage_path}")
        return storage_path


def get_public_url(storage_path):
    """Generate a public URL for a file in Supabase Storage."""
    response = supabase.storage.from_(supabase_bucket).get_public_url(storage_path)
    if not response:
        print(f"Error getting public URL.")
        return None
    else:
        return response


def list_tracks_for_song(song_id):
    """List all tracks associated with a specific song ID from Supabase storage."""
    try:
        # Assuming files are stored under directories named after song_id
        response = supabase.storage.from_(supabase_bucket).list(path=song_id)
        
        if response:
            # Extract the track information and build a list of track details
            tracks = [
                {
                    "name": item['name'],
                    "url": supabase.storage.from_(supabase_bucket).get_public_url(f"{song_id}/{item['name']}")
                }
                for item in response
            ]
            return tracks
        else:
            return None
    except Exception as e:
        print(f"Error retrieving tracks for song_id {song_id}: {e}")
        return None