import os
import time
import sys
import json
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION LOADING ---
load_dotenv()

# Load credentials from .env
CLIENT_ID = os.getenv('AWEBER_CLIENT_ID')
CLIENT_SECRET = os.getenv('AWEBER_CLIENT_SECRET')
REDIRECT_URI = os.getenv('AWEBER_REDIRECT_URI', 'http://localhost')
OUTPUT_FILE = os.getenv('OUTPUT_FILE', 'aweber_dump.md')

# Token Cache File
TOKEN_FILE = 'aweber_token.json'

# AWeber API Endpoints
AUTH_URL = os.getenv('AUTHORIZATION_BASE_URL', 'https://auth.aweber.com/oauth2/authorize')
TOKEN_URL = os.getenv('TOKEN_URL', 'https://auth.aweber.com/oauth2/token')
API_BASE = os.getenv('API_BASE', 'https://api.aweber.com/1.0')

# --- PERMISSIONS (SCOPES) ---
SCOPES = [
    'account.read',
    'list.read',
    'email.read'
]

if not CLIENT_ID or not CLIENT_SECRET or 'place_your' in CLIENT_ID:
    print("❌ CONFIGURATION ERROR: Please update your .env file with CLIENT_ID and CLIENT_SECRET.")
    sys.exit(1)

def clean_html(html_content):
    """
    Parses HTML to extract:
    1. The 'Preheader/Preview' text (often hidden in meta tags or divs).
    2. The main body text.
    """
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # --- EXTRACT PREVIEW TEXT ---
    preview_text = None

    # Strategy 1: Check <meta name="x-preheader"> (AWeber specific/Standard)
    meta_pre = soup.find('meta', attrs={'name': 'x-preheader'})
    if meta_pre and meta_pre.get('content'):
        preview_text = meta_pre.get('content').strip()

    # Strategy 2: Check for hidden divs with class 'preheader' if meta failed
    if not preview_text:
        # Look for class or id containing "preheader"
        for tag in soup.find_all(attrs={"class": lambda x: x and 'preheader' in x.lower()}):
            if tag.get_text(strip=True):
                preview_text = tag.get_text(strip=True)
                break

    # --- CLEAN BODY ---
    # Remove script and style elements to reduce noise
    for script in soup(["script", "style"]):
        script.extract()

    # Get text
    body_text = soup.get_text(separator='\n\n', strip=True)
    
    # Construct final output
    final_output = ""
    if preview_text:
        final_output += f"**Preview Text:** {preview_text}\n\n---\n\n"
    
    final_output += body_text
    
    return final_output

def save_token(token):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token, f)
    print("💾 Token cached locally.")

def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            token = json.load(f)
        if token.get('expires_at') and token['expires_at'] > time.time():
            print("⚡ Loaded valid token from cache.")
            return token
        else:
            print("⚠️ Cached token expired.")
            return None
    except Exception as e:
        print(f"⚠️ Error loading token cache: {e}")
        return None

def main():
    print("🚀 AWeber Dumper v1.7 (Preview Text Extractor)")

    # --- STEP 1: OAUTH FLOW ---
    token = load_token()
    aweber = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPES, token=token)

    if not token:
        authorization_url, state = aweber.authorization_url(AUTH_URL)
        print("\n🔐 Authorization Required.")
        print(f"1. Login here:\n   {authorization_url}")
        print("2. Paste the full redirect URL here:")
        redirect_response = input("   > ").strip()

        try:
            token = aweber.fetch_token(TOKEN_URL, client_secret=CLIENT_SECRET, authorization_response=redirect_response)
            save_token(token)
            print("✅ Token acquired.")
        except Exception as e:
            print(f"❌ Auth Error: {e}")
            sys.exit(1)

    # --- STEP 2: ACCOUNT & LIST ---
    print("\n🔍 Connecting to API...")
    try:
        accounts_resp = aweber.get(f'{API_BASE}/accounts')
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        sys.exit(1)
    
    if accounts_resp.status_code == 401:
        print("❌ Token expired/invalid (401). Please delete 'aweber_token.json' and retry.")
        sys.exit(1)
        
    if accounts_resp.status_code != 200:
        print(f"❌ API Error: {accounts_resp.status_code}")
        sys.exit(1)

    accounts_data = accounts_resp.json()
    if not accounts_data.get('entries'):
        print("❌ No account found.")
        sys.exit(1)

    account = accounts_data['entries'][0]
    account_id = account.get('id')
    
    lists_resp = aweber.get(account['lists_collection_link'])
    lists_data = lists_resp.json()
    
    if not lists_data.get('entries'):
        print("❌ No lists found.")
        sys.exit(1)

    target_list = lists_data['entries'][0]
    list_id = target_list['id']
    print(f"📝 List: {target_list['name']} (ID: {list_id})")

    # --- STEP 3: FETCH BROADCASTS ---
    base_broadcasts_link = f"{API_BASE}/accounts/{account_id}/lists/{list_id}/broadcasts"
    STATUSES_TO_FETCH = ['draft', 'scheduled', 'sent'] 
    
    collected_messages = []

    for status in STATUSES_TO_FETCH:
        print(f"\n📥 Fetching '{status}' messages...")
        current_link = base_broadcasts_link
        params = {'status': status}
        
        while current_link:
            request_params = params if current_link == base_broadcasts_link else None
            resp = aweber.get(current_link, params=request_params)
            
            if resp.status_code != 200:
                if resp.status_code == 404:
                    print(f"   ℹ️  None found.")
                else:
                    print(f"⚠️ Error {resp.status_code}")
                break
                
            page_data = resp.json()
            entries = page_data.get('entries', [])

            for entry in entries:
                self_link = entry.get('self_link') or f"{base_broadcasts_link}/{entry.get('broadcast_id')}"
                
                if self_link:
                    detail_resp = aweber.get(self_link)
                    if detail_resp.status_code == 200:
                        d = detail_resp.json()
                        
                        subject = d.get('subject', '(No Subject)')
                        msg_status = d.get('status', status)
                        date_str = d.get('sent_at') or d.get('scheduled_for') or 'N/A'
                        
                        # Use updated clean_html to extract preview text
                        clean_text = clean_html(d.get('body_html'))

                        collected_messages.append({
                            'subject': subject,
                            'date': date_str,
                            'status': msg_status,
                            'content': clean_text
                        })
                        print(f"   ✓ {subject[:40]}... [{date_str}]")
                time.sleep(0.1)

            current_link = page_data.get('next_collection_link')
            params = None

    # --- STEP 4: SAVE TO FILE ---
    if collected_messages:
        # Sort descending (Newest First)
        print("\n🗂️  Sorting messages chronologically...")
        collected_messages.sort(key=lambda x: x['date'], reverse=True)

        print(f"💾 Saving {len(collected_messages)} messages to: {OUTPUT_FILE}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(f"# AWeber Export\nList: {target_list['name']}\nDate: {time.strftime('%Y-%m-%d')}\n\n")
            
            for i, msg in enumerate(collected_messages, 1):
                f.write(f"---\n## {i}. {msg['subject']}\n")
                f.write(f"- **Date:** {msg['date']}\n")
                f.write(f"- **Status:** {msg['status']}\n\n")
                f.write(f"### Content:\n{msg['content']}\n\n")
        print("🎉 Done!")
    else:
        print("⚠️ Nothing to save.")

if __name__ == "__main__":
    main()