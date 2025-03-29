import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secure-default-key')
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/farmersmarket')
    
    # File upload configuration
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8MB
    
    