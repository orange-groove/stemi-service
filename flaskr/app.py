from flask import Flask
from flaskr.config import Config
from flaskr.routes import routes_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)  # Load the config

    # Register the routes blueprint with /api/v1 prefix
    app.register_blueprint(routes_bp, url_prefix='/api/v1')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
