import os
# This path is standard Windows AppData, so it's hidden and separate per user
app_data_path = os.path.join(os.getenv('LOCALAPPDATA'), 'TechAce')
os.makedirs(app_data_path, exist_ok=True)

CONFIG_FILE = os.path.join(app_data_path, "techace_config.json")
COOKIE_FILE = os.path.join(app_data_path, "moodle_cookies.json")
CHROME_DATA_DIR = os.path.join(app_data_path, "techace_chrome_data")