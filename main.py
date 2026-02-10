import os
import datetime
import re
import json
import sys
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Initial debug print to verify script execution
print("--- [DEBUG] Script process started ---")

# --- Configuration ---
WEBHOOK_URL = os.environ.get("MACRODROID_WEBHOOK_URL")
TARGET_COLOR_ID = '1' # Lavender
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def check_files_integrity():
    """Checks if secret files exist and contain valid JSON format."""
    print("--- [DEBUG] Checking file integrity...")
    
    files = ['token.json', 'credentials.json']
    for filename in files:
        if not os.path.exists(filename):
            print(f"❌ ERROR: {filename} does not exist!")
            continue
            
        # Check file size
        size = os.path.getsize(filename)
        if size == 0:
            print(f"❌ ERROR: {filename} is empty (0 bytes)!")
            continue
            
        # Check JSON validity
        try:
            with open(filename, 'r') as f:
                content = json.load(f)
                print(f"✅ {filename} is valid JSON. Keys found: {list(content.keys())}")
        except json.JSONDecodeError as e:
            print(f"❌ ERROR: {filename} contains invalid JSON! Error: {e}")
            print("Make sure you pasted the content correctly in GitHub Secrets without extra spaces.")

def get_calendar_service():
    """Authenticates and returns the Google Calendar service object."""
    print("--- [DEBUG] Attempting to connect to Google Calendar...")
    creds = None
    
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            print("--- [DEBUG] Loaded credentials from token.json")
        except Exception as e:
            print(f"❌ ERROR loading token.json: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("--- [DEBUG] Token expired, refreshing...")
            try:
                creds.refresh(Request())
                print("--- [DEBUG] Token refreshed successfully.")
            except Exception as e:
                print(f"❌ ERROR refreshing token: {e}")
                return None
        else:
            print("❌ ERROR: No valid token found and cannot refresh headless.")
            return None
            
    try:
        service = build('calendar', 'v3', credentials=creds)
        print("--- [DEBUG] Service built successfully.")
        return service
    except Exception as e:
        print(f"❌ ERROR building service: {e}")
        return None

def extract_phone_number(text):
    """Extracts an Israeli phone number (05X-XXXXXXX) from the text."""
    if not text: return None
    match = re.search(r'(05\d-?\d{7})', text)
    return match.group(1) if match else None

def get_tomorrow_range():
    """Calculates the start and end time for tomorrow (Israel Time)."""
    # Calculate time based on UTC
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    # Manually adjust to Israel Time (UTC+2) to ensure correct date calculation
    israel_time = utc_now + datetime.timedelta(hours=2)
    
    today_date = israel_time.date()
    tomorrow = today_date + datetime.timedelta(days=1)
    
    # Format for Google API (must be in UTC format 'Z')
    time_min = f"{tomorrow}T00:00:00Z"
    time_max = f"{tomorrow}T23:59:59Z"
    
    print(f"--- [DEBUG] Calculation: Now(IL)={israel_time}, Search Target={tomorrow}")
    return time_min, time_max

def main():
    try:
        print(f"--- [DEBUG] Webhook configured: {bool(WEBHOOK_URL)}")
        if not WEBHOOK_URL:
            print("❌ ERROR: Webhook URL missing.")
            return

        # Run file integrity check before proceeding
        check_files_integrity()

        service = get_calendar_service()
        if not service:
            print("❌ CRITICAL: Failed to connect to Calendar service. Exiting.")
            return

        time_min, time_max = get_tomorrow_range()
        print(f"--- [DEBUG] Querying range: {time_min} to {time_max}")

        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"--- [DEBUG] Events found count: {len(events)}")
        
        if not events:
            print("--- [INFO] No events found in range.")
            return

        for event in events:
            summary = event.get('summary', 'No Title')
            description = event.get('description', '')
            color_id = event.get('colorId', None)
            
            print(f"--- [DEBUG] Checking event: {summary} | Color: {color_id}")

            raw_start_time = event.get('start', {}).get('dateTime')
            if raw_start_time:
                dt_object = datetime.datetime.fromisoformat(raw_start_time)
                formatted_time = dt_object.strftime('%H:%M')
            else:
                formatted_time = "במהלך היום"

            # Filter by Color: Skip if color is present AND not Lavender (ID 1)
            if color_id and color_id != TARGET_COLOR_ID:
                print(f"    -> Skipped (Color mismatch)")
                continue

            phone = extract_phone_number(description)
            if phone:
                print(f"    -> MATCH! Found phone: {phone}")
                # Message content remains in Hebrew for the client
                message_text = f"היי {summary}, תזכורת לתור שלך מחר בשעה {formatted_time} לתספורת אצלי! נתראה :)"
                try:
                    resp = requests.get(WEBHOOK_URL, params={"phone": phone, "msg": message_text})
                    print(f"    -> Webhook sent! Status: {resp.status_code}")
                except Exception as e:
                    print(f"❌ ERROR sending webhook: {e}")
            else:
                print(f"    -> Skipped (No phone number)")

    except Exception as e:
        print(f"❌ CRITICAL ERROR IN MAIN: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
