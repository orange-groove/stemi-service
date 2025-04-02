import os
from flask import Flask
from flask_cors import CORS
from flaskr.config import Config
from flaskr.routes import routes_bp

def create_app():
    app = Flask(__name__)
    CORS(app)
    app.config.from_object(Config)  # Load the config

    # Register the routes blueprint with /api/v1 prefix
    app.register_blueprint(routes_bp, url_prefix='/api/v1')

    @app.route('/healthz', methods=['GET'])
    def healthz():
        return 'Ok'

    app.debug = True

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
