import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError, InvalidAudienceError
from flask import request, jsonify
from functools import wraps
from flaskr.config import Config  # Adjust to your config file

def authorize(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authorization token is missing or invalid"}), 401

        token = auth_header.split(" ")[1]

        try:
            # Decode the token, expecting the audience "authenticated"
            decoded_token = jwt.decode(
                token,
                Config.SECRET_KEY,
                algorithms=["HS256"],
                audience="authenticated"  # Replace with your audience if different
            )
            request.user_id = decoded_token.get('sub')  # Attach user_id to the request object
        except ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except InvalidAudienceError:
            return jsonify({"error": "Invalid audience"}), 401
        except InvalidTokenError as e:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated
