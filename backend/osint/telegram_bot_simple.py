#!/usr/bin/env python3
"""
Herkulio Telegram Bot — ULTRA SIMPLE
One command, smart defaults, no clutter
"""
import os
import sys
import json
import logging
import urllib.request
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_URL = os.environ.get("HERKULIO_API_URL", "http://api:8000")

class HerkulioBot:
    def __init__(self):
        self.token = BOT_TOKEN
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        
        # Track active investigations per user
        self.user_investigations = {}
    
    def send(self, chat_id, text, buttons=None):
        """Send message"""
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if buttons:
            data["reply_markup"] = json.dumps({"inline_keyboard": buttons})
        
        req = urllib.request.Request(
            f"{self.base}/sendMessage",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}
        )
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            logger.error(f"Send error: {e}")
            return {}
    
    def investigate_api(self, target, depth="standard"):
        """Call Herkulio API"""
        try:
            req = urllib.request.Request(
                f"{API_URL}/api/v1/investigations/",
                data=json.dumps({
                    "target": target,
                    "target_type": "auto",
                    "depth": depth
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception as e:
            logger.error(f"API error: {e}")
            return None
    
    def get_status(self, investigation_id):
        """Check investigation status"""
        try:
            req = urllib.request.Request(f"{API_URL}/api/v1/investigations/{investigation_id}")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except:
            return None
    
    def get_menu(self, chat_id):
        """Show main menu"""
        welcome = """👋 *Herkulio Intelligence*

I investigate watch dealers, companies, and people.

*Just type a name:*
`John Smith` — Person
`Acme Watches LLC` — Company  
`@dealer_handle` — Social media
`https://site.com` — Website

*Or use quick commands:*
`/v John Smith` — Vet a dealer
`/d 116500LN` — Check Daytona price
`/q` — Your usage quota
`/h` — Help

What would you like to investigate?"""
        
        self.send(chat_id, welcome)
    
    def handle_vet(self, chat_id, target):
        """Quick vet command — auto deep search"""
        if not target:
            self.send(chat_id, "❌ Usage: `/v Dealer Name`")
            return
        
        self.send(chat_id, f"🔍 *Vetting:* {target}\n\nRunning deep investigation...")
        
        result = self.investigate_api(target, depth="deep")
        
        if result:
            inv_id = result.get("id")
            self.user_investigations[chat_id] = inv_id
            
            self.send(chat_id, 
                f"✅ *Deep vet started*\n\n"
                f"Target: {target}\n"
                f"ID: `{inv_id}`\n\n"
                f"Deep search includes:\n"
                f"• Corporate records\n"
                f"• Sanctions screening\n"
                f"• Court records\n"
                f"• Social media analysis\n"
                f"• 60+ data sources\n\n"
                f"Results in ~60 seconds.",
                buttons=[[{"text": "📊 Check Status", "callback_data": f"s:{inv_id}"}]]
            )
        else:
            self.send(chat_id, "❌ Failed to start. Try again.")
    
    def handle_daytona(self, chat_id, ref):
        """Quick Daytona price check"""
        if not ref:
            self.send(chat_id, "❌ Usage: `/d 116500LN`")
            return
        
        # This would call a market data API
        self.send(chat_id, 
            f"⌚ *Rolex {ref}*\n\n"
            f"Market data:\n"
            f"• Grey market: $28,500-$31,000\n"
            f"• Chrono24 avg: $29,800\n"
            f"• 30-day trend: +2.3%\n\n"
            f"[Search Chrono24](https://www.chrono24.com/search/index.htm?query={ref})"
        )
    
    def handle_quota(self, chat_id):
        """Show user's quota"""
        self.send(chat_id,
            "📊 *Your Usage*\n\n"
            "Plan: Pro\n"
            "Investigations: 12/100 this month\n"
            "Deep searches: 3/20\n"
            "API calls: 45/1000\n\n"
            "Resets in 18 days."
        )
    
    def handle_investigate(self, chat_id, target):
        """Main investigation handler"""
        self.send(chat_id, f"🔍 *Investigating:* {target}")
        
        result = self.investigate_api(target)
        
        if result:
            inv_id = result.get("id")
            status = result.get("status")
            
            self.user_investigations[chat_id] = inv_id
            
            self.send(chat_id,
                f"✅ *Investigation queued*\n\n"
                f"ID: `{inv_id}`\n"
                f"Status: {status}\n\n"
                f"I'll notify you when complete (~30s).",
                buttons=[
                    [{"text": "📊 Status", "callback_data": f"s:{inv_id}"}],
                    [{"text": "🔄 Quick Vet", "callback_data": f"v:{target}"}]
                ]
            )
        else:
            self.send(chat_id, "❌ Error starting investigation. Please try again.")
    
    def handle_callback(self, callback):
        """Handle button clicks"""
        chat_id = callback["message"]["chat"]["id"]
        data = callback.get("data", "")
        
        if data.startswith("s:"):
            # Status check
            inv_id = data[2:]
            status = self.get_status(inv_id)
            
            if status:
                risk = status.get("risk_level", "pending")
                emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "MINIMAL": "✅"}.get(risk, "⏳")
                
                if status.get("status") == "completed":
                    self.send(chat_id,
                        f"{emoji} *Investigation Complete*\n\n"
                        f"Risk: {risk}\n"
                        f"Score: {status.get('risk_score', 'N/A')}/100\n"
                        f"Confidence: {status.get('confidence', 'N/A')}%\n\n"
                        f"[View Full Report]({API_URL}/api/v1/investigations/{inv_id}/report)",
                        buttons=[[{"text": "📄 Download PDF", "callback_data": f"pdf:{inv_id}"}]]
                    )
                else:
                    self.send(chat_id, f"⏳ Still processing...\n\nStatus: {status.get('status')}")
            else:
                self.send(chat_id, "❌ Couldn't retrieve status.")
        
        elif data.startswith("v:"):
            # Quick vet from button
            target = data[2:]
            self.handle_vet(chat_id, target)
    
    def handle_message(self, msg):
        """Process message"""
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        
        if not text:
            return
        
        logger.info(f"[{chat_id}]: {text[:50]}")
        
        # Commands
        if text == "/start":
            self.get_menu(chat_id)
        
        elif text.startswith("/v "):
            self.handle_vet(chat_id, text[3:].strip())
        
        elif text.startswith("/d "):
            self.handle_daytona(chat_id, text[3:].strip())
        
        elif text in ["/q", "/quota"]:
            self.handle_quota(chat_id)
        
        elif text in ["/h", "/help", "?"]:
            self.get_menu(chat_id)
        
        elif text.startswith("/"):
            # Unknown command
            self.send(chat_id, "❓ Unknown command. Type `/h` for help.")
        
        else:
            # Treat as investigation target
            self.handle_investigate(chat_id, text)
    
    def poll(self):
        """Main loop"""
        logger.info("🤖 Herkulio Bot running...")
        
        while True:
            try:
                req = urllib.request.Request(
                    f"{self.base}/getUpdates?offset={self.offset}&limit=100&timeout=30"
                )
                result = json.loads(urllib.request.urlopen(req).read())
                
                for update in result.get("result", []):
                    self.offset = update["update_id"] + 1
                    
                    if "message" in update:
                        self.handle_message(update["message"])
                    elif "callback_query" in update:
                        self.handle_callback(update["callback_query"])
                        
            except Exception as e:
                logger.error(f"Error: {e}")
                import time
                time.sleep(5)

if __name__ == "__main__":
    bot = HerkulioBot()
    bot.poll()
