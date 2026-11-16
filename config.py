import os # Interact with the operative system
import pytz # Time zones worldwide
from datetime import datetime # Manage dates and in general the time
from dotenv import load_dotenv # Read the .env file

# Base directory where all the stuff is saved
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Data base path
DB_PATH = os.path.join(BASE_DIR, 'estacion88.db')

# Load .env in the os memory
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Get secret variables in .env
SECRET_KEY = os.getenv('FLASK_SECRET')
ADMIN_USER = os.getenv('ADMIN_USER')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Save the correct time zone
ZONE_CDMX = pytz.timezone('America/Mexico_City')

def get_now() -> datetime:
    """Get the current time and date in Mexico City"""
    current_datetime = datetime.now(ZONE_CDMX)
    return current_datetime

def get_current_date() -> str:
    """Get the current time with format %Y-%m-%d"""
    current_datetime = get_now()
    # Give format to the datetime
    current_date = current_datetime.strftime('%Y-%m-%d')
    return current_date
