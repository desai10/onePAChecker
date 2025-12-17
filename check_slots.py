import requests
from datetime import datetime, timedelta
import json
import time
import os
from collections import defaultdict

# Base URL for the API
BASE_URL = "https://www.onepa.gov.sg/pacesapi/facilityavailability/GetFacilitySlots"

# List of facilities to check
FACILITIES = [
    "teckgheecc_BADMINTONCOURTS",
    "BidadariCC_BADMINTONCOURTS",
    "kallangcc_BADMINTONCOURTS",
    "braddellheightscc_BADMINTONCOURTS",
    "canberracc_BADMINTONCOURTS",
    "potongpasircc_BADMINTONCOURTS"
]

# Configuration
REQUEST_TIMEOUT = 10  # seconds
DELAY_BETWEEN_REQUESTS = 3  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 20  # seconds

# Telegram Configuration (from environment variables)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def send_telegram_message(message):
    """Send a message via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured, skipping notification")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Split long messages (Telegram has 4096 char limit)
    max_length = 4000
    messages = [message[i:i+max_length] for i in range(0, len(message), max_length)]
    
    for msg in messages:
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': msg,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            time.sleep(1)  # Small delay between messages
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False
    
    return True

def get_facility_slots(facility, date_str, retry_count=0):
    """
    Call the API for a specific facility and date with retry logic.
    
    Args:
        facility: The facility identifier
        date_str: Date string in DD/MM/YYYY format
        retry_count: Current retry attempt number
    
    Returns:
        Response JSON or None if error
    """
    params = {
        "selectedFacility": facility,
        "selectedDate": date_str
    }
    
    try:
        response = requests.get(
            BASE_URL, 
            params=params, 
            timeout=REQUEST_TIMEOUT,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        response.raise_for_status()
        data = response.json()
        
        # Check if the response status code is 200
        response_status = data.get("responseStatusCode")
        if (response_status != 200 and response_status != "200") and (response_status != 2008 and response_status != "2008"):
            if retry_count < MAX_RETRIES:
                print(f"Non-200 status code: {response_status} (attempt {retry_count + 1}/{MAX_RETRIES + 1})")
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
                return get_facility_slots(facility, date_str, retry_count + 1)
            else:
                print(f"Failed after {MAX_RETRIES + 1} attempts - status code: {response_status}")
                return None
        
        return data
        
    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES:
            print(f"Error (attempt {retry_count + 1}/{MAX_RETRIES + 1}): {e}")
            print(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
            return get_facility_slots(facility, date_str, retry_count + 1)
        else:
            print(f"Failed after {MAX_RETRIES + 1} attempts: {e}")
            return None

def extract_available_slots(response_data):
    """
    Extract available slots from the API response.
    
    Args:
        response_data: The JSON response from the API
    
    Returns:
        List of available slots with details
    """
    available_slots = []
    
    if not response_data or 'response' not in response_data:
        return available_slots
    
    response = response_data['response']
    resource_list = response.get('resourceList', [])
    
    for resource in resource_list:
        resource_name = resource.get('resourceName', 'Unknown')
        slot_list = resource.get('slotList', [])
        
        for slot in slot_list:
            # Check if slot is available (isAvailable == true OR availabilityStatus == "Available")
            if slot.get('isAvailable') or slot.get('availabilityStatus') == 'Available':
                available_slots.append({
                    'court': resource_name,
                    'time': slot.get('timeRangeName'),
                    'startTime': slot.get('startTime'),
                    'endTime': slot.get('endTime'),
                    'isPeak': slot.get('isPeak', False)
                })
    
    return available_slots

def format_facility_name(facility):
    """Convert facility code to readable name."""
    names = {
        "teckgheecc_BADMINTONCOURTS": "Teck Ghee CC",
        "BidadariCC_BADMINTONCOURTS": "Bidadari CC",
        "kallangcc_BADMINTONCOURTS": "Kallang CC",
        "braddellheightscc_BADMINTONCOURTS": "Braddell Heights CC",
        "canberracc_BADMINTONCOURTS": "Canberra CC",
        "potongpasircc_BADMINTONCOURTS": "Potong Pasir CC"
    }
    return names.get(facility, facility)

def check_facilities():
    """
    Check all facilities starting from today until responseStatusCode is 2008.
    Collect all available slots.
    """
    all_available_slots = defaultdict(lambda: defaultdict(list))
    
    for facility in FACILITIES:
        print(f"\n{'='*60}")
        print(f"Checking facility: {facility}")
        print(f"{'='*60}")
        
        current_date = datetime.now()
        dates_checked = 0
        
        while True:
            date_str = current_date.strftime("%d/%m/%Y")
            print(f"Checking date: {date_str}...", end=" ")
            
            data = get_facility_slots(facility, date_str)
            
            if data is None:
                print("Failed to get response after retries")
                break
            
            status_code = data.get("responseStatusCode")
            print(f"Status Code: {status_code}", end=" ")
            
            # Extract available slots
            available_slots = extract_available_slots(data)
            
            if available_slots:
                all_available_slots[facility][date_str] = {
                    'slots': available_slots,
                    'outletDivision': data.get('response', {}).get('outletDivison', ''),
                    'price': data.get('response', {}).get('price', {})
                }
                print(f"- Found {len(available_slots)} available slots!")
            else:
                print("- No available slots")
            
            dates_checked += 1
            
            # Stop if we get status code 2008
            if status_code == "2008" or status_code == 2008:
                print(f"Reached status code 2008 for {facility}")
                break
            
            # Move to next day
            current_date += timedelta(days=1)
            
            # Safety limit: stop after 5 days
            if dates_checked > 5:
                print(f"Reached safety limit of 5 days for {facility}")
                break
            
            # Delay between requests to avoid throttling
            time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # Extra delay between facilities
        print(f"\nWaiting {DELAY_BETWEEN_REQUESTS * 2} seconds before next facility...")
        time.sleep(DELAY_BETWEEN_REQUESTS * 2)
    
    return all_available_slots

def create_telegram_summary(all_slots):
    """Create a formatted summary for Telegram."""
    lines = []
    lines.append("🏸 <b>OnePA Badminton Slots Available</b> 🏸")
    lines.append(f"📅 Checked on: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
    
    total_slots = 0
    facilities_with_slots = 0
    
    for facility, dates in sorted(all_slots.items()):
        if dates:
            facilities_with_slots += 1
            facility_name = format_facility_name(facility)
            lines.append(f"\n<b>🏢 {facility_name}</b>")
            
            for date_str, date_data in sorted(dates.items()):
                slots = date_data['slots']
                price_info = date_data.get('price', {})
                
                lines.append(f"\n📆 <b>{date_str}</b>")
                
                # Group by court
                courts = defaultdict(list)
                for slot in slots:
                    courts[slot['court']].append(slot)
                
                for court, court_slots in courts.items():
                    lines.append(f"  {court}:")
                    for slot in court_slots:
                        peak = "⭐" if slot['isPeak'] else "  "
                        lines.append(f"    {peak} {slot['time']}")
                
                total_slots += len(slots)
    
    if total_slots == 0:
        lines.append("\n❌ <b>No available slots found</b>")
    else:
        lines.append(f"\n✅ <b>Total: {total_slots} slots across {facilities_with_slots} facilities</b>")
    
    lines.append(f"\n⭐ = Peak hours")
    
    return "\n".join(lines)

def save_results(all_slots, filename="available_slots.json"):
    """Save available slots to a JSON file."""
    # Convert defaultdict to regular dict for JSON serialization
    output = {
        facility: dict(dates) 
        for facility, dates in all_slots.items()
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nDetailed results saved to {filename}")

if __name__ == "__main__":
    print("Starting OnePA Facility Slots Checker")
    print(f"Current date: {datetime.now().strftime('%d/%m/%Y')}")
    print(f"\nConfiguration:")
    print(f"  - Request timeout: {REQUEST_TIMEOUT}s")
    print(f"  - Delay between requests: {DELAY_BETWEEN_REQUESTS}s")
    print(f"  - Max retries: {MAX_RETRIES}")
    print(f"  - Retry delay: {RETRY_DELAY}s")
    print(f"  - Telegram enabled: {bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}")
    
    try:
        all_slots = check_facilities()
        save_results(all_slots)
        
        # Send Telegram notification
        summary = create_telegram_summary(all_slots)
        print("\n" + "="*60)
        print("TELEGRAM SUMMARY")
        print("="*60)
        print(summary.replace('<b>', '').replace('</b>', ''))
        
        if send_telegram_message(summary):
            print("\n✓ Telegram notification sent successfully!")
        
        print("\n✓ Script completed successfully!")
        
    except Exception as e:
        error_msg = f"❌ <b>Error running OnePA checker</b>\n\n{str(e)}"
        print(f"\n❌ Error: {e}")
        send_telegram_message(error_msg)
