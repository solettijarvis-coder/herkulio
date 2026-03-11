#!/usr/bin/env python3
"""
Herkulio Telegram Bot - Production Ready (Simplified)
Standalone version without complex agent dependencies
"""
import os
import sys
import json
import logging
import urllib.request
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config from environment
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set!")
    sys.exit(1)

API_URL = os.environ.get("HERKULIO_API_URL", "http://api:8000")

class HerkulioBot:
    def __init__(self):
        self.token = BOT_TOKEN
        self.api_base = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        
    def tg_api(self, method, **params):
        """Call Telegram API"""
        url = f"{self.api_base}/{method}"
        data = json.dumps(params).encode()
        req = urllib.request.Request(
            url, 
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except Exception as e:
            logger.error(f"Telegram API error: {e}")
            return {}
    
    def send_message(self, chat_id, text, buttons=None):
        """Send message to user"""
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if buttons:
            params["reply_markup"] = json.dumps({
                "inline_keyboard": buttons
            })
        return self.tg_api("sendMessage", **params)
    
    def send_investigation_request(self, chat_id, target, target_type="auto", depth="standard"):
        """Send investigation request to Herkulio API"""
        import urllib.request
        
        url = f"{API_URL}/api/v1/investigations/"
        data = json.dumps({
            "target": target,
            "target_type": target_type,
            "depth": depth
        }).encode()
        
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read())
        except Exception as e:
            logger.error(f"API error: {e}")
            return None
    
    def handle_start(self, chat_id, user):
        """Handle /start command"""
        welcome = f"""👋 Welcome to *Herkulio Intelligence*!

I'm your OSINT research assistant. I can investigate:
• People (dealers, collectors, brokers)
• Companies (businesses, shell corporations)  
• Watch listings and sellers

*Quick start:*
Type any name, company, or URL to start investigating.

*Examples:*
`/investigate John Smith`
`/investigate Acme Watches LLC`
`/investigate https://example.com`

Your investigations are private and secure."""
        
        self.send_message(chat_id, welcome)
    
    def handle_investigate(self, chat_id, text):
        """Handle investigation request"""
        # Parse command: /investigate <target>
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            self.send_message(
                chat_id,
                "❌ Please provide a target.\n\nExample: `/investigate John Smith`"
            )
            return
        
        target = parts[1].strip()
        
        # Send acknowledgment
        self.send_message(
            chat_id,
            f"🔍 Starting investigation: *{target}*\n\nThis may take 30-60 seconds..."
        )
        
        # Call API
        result = self.send_investigation_request(chat_id, target)
        
        if result:
            investigation_id = result.get("id", "unknown")
            status = result.get("status", "pending")
            
            self.send_message(
                chat_id,
                f"✅ Investigation started!\n\n"
                f"ID: `{investigation_id}`\n"
                f"Status: {status}\n\n"
                f"You'll receive results when complete.",
                buttons=[
                    [{"text": "📊 Check Status", "callback_data": f"status:{investigation_id}"}]
                ]
            )
        else:
            self.send_message(
                chat_id,
                "❌ Failed to start investigation. Please try again later."
            )
    
    def handle_message(self, message):
        """Process incoming message"""
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        user = message.get("from", {})
        
        logger.info(f"Message from {chat_id}: {text[:50]}...")
        
        # Handle commands
        if text.startswith("/start"):
            self.handle_start(chat_id, user)
        elif text.startswith("/investigate"):
            self.handle_investigate(chat_id, text)
        elif text.startswith("/help"):
            self.handle_start(chat_id, user)  # Show welcome again
        else:
            # Treat as investigation request
            self.handle_investigate(chat_id, f"/investigate {text}")
    
    def poll(self):
        """Main polling loop"""
        logger.info("🤖 Herkulio Bot starting...")
        
        while True:
            try:
                # Get updates
                result = self.tg_api(
                    "getUpdates",
                    offset=self.offset,
                    limit=100,
                    timeout=30
                )
                
                updates = result.get("result", [])
                
                for update in updates:
                    self.offset = update["update_id"] + 1
                    
                    if "message" in update:
                        self.handle_message(update["message"])
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(5)

if __name__ == "__main__":
    import time
    bot = HerkulioBot()
    bot.poll()
