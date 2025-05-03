from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, StickerMessage,
    TextSendMessage, ImageSendMessage
)
import threading
import logging
import requests
import os
import tempfile
from pathlib import Path
import json
import traceback
import time

from deltachat_rpc_client import Bot, DeltaChat, Rpc, events

# --- Environment configuration ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
MY_DC_EMAIL = os.environ.get('MY_DC_EMAIL')
NGROK_URL = os.environ.get('NGROK_URL', 'https://your-ngrok-domain.ngrok-free.app')
DELTACHAT_RPC_HOST = os.environ.get('DELTACHAT_RPC_HOST', '127.0.0.1')
DELTACHAT_RPC_PORT = os.environ.get('DELTACHAT_RPC_PORT', '23123')

# Constants
CHAT_MAPPING_FILE = '/tmp/chat_mapping.json'

# Global variables
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
hooks = events.HookCollection()
deltachat_account = None
app = Flask(__name__, static_folder='/tmp')

# Group chat cache
group_chat_cache = {}
group_to_line_userid = {}

def load_chat_mapping():
    """Load saved chat mappings"""
    global group_to_line_userid, group_chat_cache
    try:
        # Skip if deltachat_account is not initialized yet
        if deltachat_account is None:
            logging.warning("Delta Chat account not initialized yet, skipping chat mapping load")
            return
            
        if os.path.exists(CHAT_MAPPING_FILE):
            with open(CHAT_MAPPING_FILE, 'r') as f:
                mapping = json.load(f)
                group_to_line_userid = {int(k): v for k, v in mapping.items()}
                logging.info(f"Loaded chat mappings: {len(group_to_line_userid)} entries")
                
                # Restore existing group chats
                chats = deltachat_account.get_chatlist()
                for chat in chats:
                    if getattr(chat, "is_group", False) and chat.id in group_to_line_userid:
                        user_id = group_to_line_userid[chat.id]
                        dc_addr = f"line+{user_id}@example.com"
                        group_chat_cache[dc_addr] = chat
                        logging.info(f"Restored existing group chat: {chat.id} -> {dc_addr}")
    except Exception as e:
        logging.error(f"Error loading chat mappings: {e}")
        traceback.print_exc()

def save_chat_mapping():
    """Save chat mappings"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(CHAT_MAPPING_FILE), exist_ok=True)
        
        with open(CHAT_MAPPING_FILE, 'w') as f:
            json.dump(group_to_line_userid, f)
            logging.info(f"Saved chat mappings: {len(group_to_line_userid)} entries")
    except Exception as e:
        logging.error(f"Error saving chat mappings: {e}")
        traceback.print_exc()

def find_existing_group_for_line_user(user_id):
    """Find existing group for LINE user (improved version)"""
    dc_addr = f"line+{user_id}@example.com"
    
    # Search in mappings
    for chat_id, mapped_user_id in group_to_line_userid.items():
        if mapped_user_id == user_id:
            chats = deltachat_account.get_chatlist()
            for chat in chats:
                if chat.id == chat_id:
                    logging.info(f"Found existing group from mapping: {chat.id} -> {user_id}")
                    return chat
    
    # Search by membership (even if not in mapping)
    chats = deltachat_account.get_chatlist()
    for chat in chats:
        if getattr(chat, "is_group", False):
            try:
                members = set(getattr(chat, "get_members", lambda: [])())
                logging.info(f"Checking members for group {chat.id}")
                if dc_addr in members:
                    logging.info(f"Found existing group from membership: {chat.id} -> {user_id}")
                    # Update mapping
                    group_to_line_userid[chat.id] = user_id
                    save_chat_mapping()
                    return chat
            except Exception as e:
                logging.error(f"Error checking group members: {e}")
                continue
    
    return None

def get_or_create_group_chat(dc_addr, user_id):
    """Get existing group chat or create a new one"""
    global deltachat_account, group_to_line_userid
    
    # Check cache
    if dc_addr in group_chat_cache:
        return group_chat_cache[dc_addr]
    
    # Search for existing group chat
    chats = deltachat_account.get_chatlist()
    for chat in chats:
        if getattr(chat, "is_group", False):
            try:
                members = set(getattr(chat, "get_members", lambda: [])())
                if dc_addr in members and MY_DC_EMAIL in members:
                    logging.info(f"Found existing group chat: chat_id={chat.id}")
                    group_chat_cache[dc_addr] = chat
                    if chat.id not in group_to_line_userid:
                        group_to_line_userid[chat.id] = user_id
                        save_chat_mapping()
                    return chat
            except Exception as e:
                logging.error(f"Error getting group members: {e}")
                continue

    # Get LINE user information
    try:
        profile = line_bot_api.get_profile(user_id)
        group_title = f"LINE: {profile.display_name}"
        picture_url = profile.picture_url
    except Exception as e:
        logging.error(f"Error getting LINE profile: {e}")
        group_title = f"LINE: {user_id}"
        picture_url = None

    # Create new group chat
    try:
        logging.info(f"Creating new group chat: {group_title}")
        chat = deltachat_account.create_group(group_title)
        chat.add_contact(dc_addr)
        chat.add_contact(MY_DC_EMAIL)
        
        # Save group chat and LINE User ID mapping
        group_chat_cache[dc_addr] = chat
        group_to_line_userid[chat.id] = user_id
        save_chat_mapping()
        
        # Set group image
        if picture_url:
            img_path = f"/tmp/line_{user_id}.jpg"
            try:
                img_data = requests.get(picture_url).content
                with open(img_path, "wb") as f:
                    f.write(img_data)
                chat.set_image(img_path)
                os.remove(img_path)
            except Exception as e:
                logging.error(f"Error setting group image: {e}")
        
        return chat
        
    except Exception as e:
        logging.error(f"Error creating group: {e}")
        raise

def send_to_deltachat(content, user_id, message_type="text"):
    """Send message from LINE to Delta Chat"""
    global deltachat_account
    dc_addr = f"line+{user_id}@example.com"
    
    try:
        # First search for existing group
        chat = find_existing_group_for_line_user(user_id)
        
        # Create new one only if not found
        if not chat:
            logging.info(f"No existing group found, creating new one: {user_id}")
            chat = get_or_create_group_chat(dc_addr, user_id)
        else:
            # Update cache
            group_chat_cache[dc_addr] = chat
            
        if message_type == "text":
            chat.send_message(text=content)
            logging.info(f"Sent text message: {content}")
        elif message_type in ["image", "sticker"]:
            chat.send_message(file=content)
            logging.info(f"Sent image: {content}")
    except Exception as e:
        logging.error(f"Error sending message to Delta Chat: {e}")
        traceback.print_exc()

def send_to_line(content, chat_id=None, message_type="text"):
    """Send message from Delta Chat to LINE"""
    try:
        if chat_id and chat_id in group_to_line_userid:
            user_id = group_to_line_userid[chat_id]
            if message_type == "text":
                message = TextSendMessage(text=content)
                line_bot_api.push_message(user_id, message)
                logging.info(f"Sent text message: {content} to {user_id}")
            elif message_type == "image":
                temp_dir = "/tmp/images"
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = f"{temp_dir}/{Path(content).name}"
                os.system(f"cp {content} {temp_path}")
                
                message = ImageSendMessage(
                    original_content_url=f"{NGROK_URL}/images/{Path(content).name}",
                    preview_image_url=f"{NGROK_URL}/images/{Path(content).name}"
                )
                line_bot_api.push_message(user_id, message)
                logging.info(f"Sent image: {content} to {user_id}")
    except Exception as e:
        logging.error(f"Error sending to LINE: {e}")
        traceback.print_exc()

@hooks.on(events.NewMessage(func=lambda e: not e.command))
def on_deltachat_message(event):
    """Handler for Delta Chat messages"""
    snapshot = event.message_snapshot
    
    if not (getattr(snapshot, "from_addr", None) == MY_DC_EMAIL or
            getattr(snapshot, "is_outgoing", False) or 
            getattr(snapshot, "from_addr", None) is None):
        return

    chat_id = getattr(snapshot, "chat_id", None)
    
    if snapshot.text:
        send_to_line(snapshot.text, chat_id, "text")
        
    file_path = getattr(snapshot, "file", None)
    if file_path and os.path.exists(file_path):
        send_to_line(file_path, chat_id, "image")

@app.route("/")
def health_check():
    """Health check endpoint"""
    return "LINE-DeltaChat Bridge is running", 200

@app.route("/callback", methods=['POST'])
def callback():
    """LINE webhook callback"""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK', 200

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve image files"""
    return send_from_directory('/tmp/images', filename)

@handler.add(MessageEvent)
def handle_message(event):
    """Handler for LINE messages"""
    user_id = event.source.user_id
    logging.info(f"LINE USER ID: {user_id}")

    if isinstance(event.message, TextMessage):
        send_to_deltachat(event.message.text, user_id, "text")
        
    elif isinstance(event.message, ImageMessage):
        message_content = line_bot_api.get_message_content(event.message.id)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as fp:
            for chunk in message_content.iter_content():
                fp.write(chunk)
            send_to_deltachat(fp.name, user_id, "image")
            os.unlink(fp.name)
            
    elif isinstance(event.message, StickerMessage):
        sticker_id = event.message.sticker_id
        sticker_url = f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/android/sticker.png"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as fp:
            img_data = requests.get(sticker_url).content
            fp.write(img_data)
            send_to_deltachat(fp.name, user_id, "sticker")
            os.unlink(fp.name)

def run_deltachat(email, password):
    """Run Delta Chat client"""
    global deltachat_account
    try:
        logging.info(f"Starting Delta Chat with email: {email}")
        
        # Connect to the DeltaChat RPC server
        logging.info(f"Connecting to DeltaChat RPC server at {DELTACHAT_RPC_HOST}:{DELTACHAT_RPC_PORT}")
        with Rpc(addr=f"{DELTACHAT_RPC_HOST}:{DELTACHAT_RPC_PORT}") as rpc:
            deltachat = DeltaChat(rpc)
            accounts = deltachat.get_all_accounts()
            logging.info(f"Found {len(accounts)} existing accounts")
            account = accounts[0] if accounts else deltachat.add_account()
            bot = Bot(account, hooks)
            if not bot.is_configured():
                logging.info("Configuring new bot account")
                bot.configure(email=email, password=password)
            else:
                logging.info("Using existing bot configuration")
            deltachat_account = account
            
            # Load chat mapping after account is initialized
            load_chat_mapping()
            
            logging.info("Starting Delta Chat bot - running forever")
            bot.run_forever()
    except Exception as e:
        logging.error(f"Error in Delta Chat thread: {e}")
        traceback.print_exc()
        # Don't exit - keep the thread running
        logging.info("Entering recovery loop to keep thread alive")
        while True:
            time.sleep(60)
            logging.info("Delta Chat recovery heartbeat...")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    import sys
    if len(sys.argv) < 3:
        print("Usage: python app.py <deltachat_email> <deltachat_password>")
        exit(1)
    
    # Create directory for images
    os.makedirs("/tmp/images", exist_ok=True)
    
    email = sys.argv[1]
    password = sys.argv[2]
    logging.info(f"Starting DeltaChat thread with email: {email}")
    
    dc_thread = threading.Thread(target=run_deltachat, args=(email, password), daemon=True)
    dc_thread.start()
    
    logging.info("Starting Flask server")
    app.run(host="0.0.0.0", port=5000)