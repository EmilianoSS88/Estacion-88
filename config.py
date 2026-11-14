import os # Interact with the operative system
import pytz # Time zones worldwide
from datetime import datetime # Manage dates and in general the time
from dotenv import load_dotenv # Read the .env file

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
print(BASE_DIR)

# 
os.path.join(BASE_DIR, '.env')