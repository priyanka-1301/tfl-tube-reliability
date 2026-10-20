import os
import requests
from dotenv import load_dotenv

# Read the secret key from the .env file
load_dotenv()
app_key = os.getenv("TFL_APP_KEY")

# Ask TfL for the status of every Tube line
url = "https://api.tfl.gov.uk/Line/Mode/tube/Status"
response = requests.get(url, params={"app_key": app_key}, timeout=30)

print("Status code:", response.status_code)

# Print each line's name and its current status
for line in response.json():
    status = line["lineStatuses"][0]["statusSeverityDescription"]
    print(f"{line['name']}: {status}")