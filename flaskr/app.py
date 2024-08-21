import os
import io
from flask import Flask, send_file, request
from flaskr.utils.helpers import separate
from shutil import rmtree
import zipfile
from pathlib import Path

UPLOAD_FOLDER = os.path.expanduser('~/test_uploads')  # Ensure the path is expanded
ALLOWED_EXTENSIONS = {'mp3', 'wav'}
SEPARATOR_CONFIG = 'spleeter:2stems'
SEPARATOR_INSTRUMENTS = ['vocals', 'accompaniment']

def create_app(test_config=None):
    # Create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config.from_mapping(
        SECRET_KEY='thisismysecret',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

    # Function to check if the file extension is allowed
    def allowed_file(filename):
        return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route('/separate', methods=['POST'])
    def separate_files():
        # Create temporary directories for input and output files
        in_path = Path('tmp_in')
        out_path = Path('tmp_out')
        
        if in_path.exists():
            rmtree(in_path)
        in_path.mkdir()
        
        if out_path.exists():
            rmtree(out_path)
        out_path.mkdir()

        # Save uploaded files to the in_path directory
        uploaded_files = request.files.getlist('file')  # 'file' should match the key in your form-data POST request
        
        for uploaded_file in uploaded_files:
            file_path = in_path / uploaded_file.filename
            uploaded_file.save(file_path)

        # Call your separation function here
        separate(in_path, out_path)
        
        # Create a ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            # Recursively add all files from the output directory
            for root, dirs, files in os.walk(out_path):
                for file in files:
                    file_path = Path(root) / file
                    zf.write(file_path, file_path.relative_to(out_path))
        
        # Move the buffer cursor to the beginning
        zip_buffer.seek(0)
        
        # Return the ZIP file as a response
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='separated_files.zip'
        )
    return app
