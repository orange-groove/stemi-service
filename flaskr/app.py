import os
import logging
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

# Load .env before importing Config so os.getenv sees values
load_dotenv()

from flaskr.config import Config
from flaskr.routes import routes_bp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    CORS(app)
    app.config.from_object(Config)  # Load the config

    # Register the routes blueprint with /api/v1 prefix
    app.register_blueprint(routes_bp, url_prefix='/api/v1')

    @app.route('/healthz', methods=['GET'])
    def healthz():
        return 'Ok', 200

    # Removed CUDA check; inference now runs on external service

    app.debug = True
    logger.info("Application created successfully")

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting application on port {port}")
    app.run(host="0.0.0.0", port=port)
