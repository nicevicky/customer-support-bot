import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
from supabase import create_client, Client
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GROUP_ID = os.getenv("GROUP_ID")

# Initialize FastAPI app
app = FastAPI(title="Telegram Customer Support Bot")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@dataclass
class BotMessage:
    message_id: int
    chat_id: int
    timestamp: datetime

class Database:
    def __init__(self):
        self.supabase = supabase

    async def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        try:
            result = self.supabase.table('users').upsert({
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name
            }).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return None

    async def add_complaint(self, user_id: int, message: str, username: str):
        try:
            result = self.supabase.table('complaints').insert({
                'user_id': user_id,
                'username': username,
                'message': message,
                'status': 'pending'
            }).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding complaint: {e}")
            return None

    async def get_complaints_stats(self):
        """Get complaints statistics"""
        try:
            # Get total complaints
            total_result = self.supabase.table('complaints').select('id', count='exact').execute()
            total_complaints = total_result.count if total_result.count else 0
            
            # Get pending complaints
            pending_result = self.supabase.table('complaints').select('id', count='exact').eq('status', 'pending').execute()
            pending_complaints = pending_result.count if pending_result.count else 0
            
            # Get resolved complaints
            resolved_result = self.supabase.table('complaints').select('id', count='exact').eq('status', 'resolved').execute()
            resolved_complaints = resolved_result.count if resolved_result.count else 0
            
            return {
                'total': total_complaints,
                'pending': pending_complaints,
                'resolved': resolved_complaints
            }
        except Exception as e:
            logger.error(f"Error getting complaints stats: {e}")
            return {'total': 0, 'pending': 0, 'resolved': 0}

    async def get_users_stats(self):
        """Get users statistics"""
        try:
            result = self.supabase.table('users').select('id', count='exact').execute()
            return result.count if result.count else 0
        except Exception as e:
            logger.error(f"Error getting users stats: {e}")
            return 0

    async def get_auto_responses_stats(self):
        """Get auto responses statistics"""
        try:
            result = self.supabase.table('auto_responses').select('id', count='exact').execute()
            return result.count if result.count else 0
        except Exception as e:
            logger.error(f"Error getting auto responses stats: {e}")
            return 0

    async def get_banned_words(self):
        try:
            result = self.supabase.table('banned_words').select('word').execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting banned words: {e}")
            return []

    async def add_banned_word(self, word: str):
        try:
            result = self.supabase.table('banned_words').insert({
                'word': word.lower()
            }).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding banned word: {e}")
            return None

    async def remove_banned_word(self, word: str):
        try:
            result = self.supabase.table('banned_words').delete().eq('word', word.lower()).execute()
            return result
        except Exception as e:
            logger.error(f"Error removing banned word: {e}")
            return None

    async def get_auto_responses(self):
        try:
            result = self.supabase.table('auto_responses').select('*').execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting auto responses: {e}")
            return []

    async def add_auto_response(self, trigger: str, response: str):
        try:
            result = self.supabase.table('auto_responses').insert({
                'trigger': trigger.lower(),
                'response': response
            }).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding auto response: {e}")
            return None

    async def add_warning(self, user_id: int, reason: str):
        try:
            result = self.supabase.table('user_warnings').insert({
                'user_id': user_id,
                'reason': reason
            }).execute()
            return result
        except Exception as e:
            logger.error(f"Error adding warning: {e}")
            return None

    async def get_user_warnings(self, user_id: int):
        try:
            result = self.supabase.table('user_warnings').select('*').eq('user_id', user_id).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting user warnings: {e}")
            return []

    async def clear_user_warnings(self, user_id: int):
        try:
            result = self.supabase.table('user_warnings').delete().eq('user_id', user_id).execute()
            return result
        except Exception as e:
            logger.error(f"Error clearing user warnings: {e}")
            return None

    async def get_group_settings(self):
        try:
            result = self.supabase.table('group_settings').select('*').limit(1).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            else:
                return {
                    'is_closed': False,
                    'max_warnings': 3,
                    'mute_duration': 60,
                    'auto_delete_minutes': 0
                }
        except Exception as e:
            logger.error(f"Error getting group settings: {e}")
            return {
                'is_closed': False,
                'max_warnings': 3,
                'mute_duration': 60,
                'auto_delete_minutes': 0
            }

    async def update_group_settings(self, settings: dict):
        try:
            existing = self.supabase.table('group_settings').select('id').limit(1).execute()
            
            settings['updated_at'] = datetime.now().isoformat()
            
            if existing.data and len(existing.data) > 0:
                settings_id = existing.data[0]['id']
                result = self.supabase.table('group_settings').update(settings).eq('id', settings_id).execute()
            else:
                result = self.supabase.table('group_settings').insert(settings).execute()
            
            return result
        except Exception as e:
            logger.error(f"Error updating group settings: {e}")
            return None

class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.db = Database()
        self.bot_messages: Dict[int, List[BotMessage]] = {}

    async def send_request(self, method: str, data: dict = None):
        """Send request to Telegram API"""
        url = f"{self.base_url}/{method}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if data:
                    response = await client.post(url, json=data)
                else:
                    response = await client.get(url)
                return response.json()
            except Exception as e:
                logger.error(f"Error sending request to Telegram: {e}")
                return None

    async def answer_callback_query(self, callback_query_id: str, text: str = None, show_alert: bool = False):
        """Answer callback query"""
        data = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert
        }
        if text:
            data["text"] = text
        
        return await self.send_request("answerCallbackQuery", data)

    async def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup: dict = None):
        """Edit message text"""
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        return await self.send_request("editMessageText", data)

    async def send_message(self, chat_id: int, text: str, reply_markup: dict = None, reply_to_message_id: int = None):
        """Send message to Telegram"""
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        if reply_markup:
            data["reply_markup"] = reply_markup
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id

        result = await self.send_request("sendMessage", data)
        
        if result and result.get("ok"):
            message_id = result["result"]["message_id"]
            await self.track_bot_message(chat_id, message_id)
        
        return result

    async def delete_message(self, chat_id: int, message_id: int):
        """Delete message"""
        data = {
            "chat_id": chat_id,
            "message_id": message_id
        }
        return await self.send_request("deleteMessage", data)

    async def restrict_chat_member(self, chat_id: int, user_id: int, until_date: int):
        """Restrict chat member"""
        data = {
            "chat_id": chat_id,
            "user_id": user_id,
            "until_date": until_date,
            "permissions": {
                "can_send_messages": False
            }
        }
        return await self.send_request("restrictChatMember", data)

    async def get_chat_member(self, chat_id: int, user_id: int):
        """Get chat member info"""
        data = {
            "chat_id": chat_id,
            "user_id": user_id
        }
        return await self.send_request("getChatMember", data)

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        """Check if user is admin in the group"""
        try:
            result = await self.get_chat_member(chat_id, user_id)
            if result and result.get("ok"):
                status = result["result"]["status"]
                return status in ["creator", "administrator"]
            return False
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    async def track_bot_message(self, chat_id: int, message_id: int):
        """Track bot message for auto-delete"""
        try:
            settings = await self.db.get_group_settings()
            auto_delete_minutes = settings.get('auto_delete_minutes', 0)
            
            if auto_delete_minutes > 0:
                bot_message = BotMessage(
                    message_id=message_id,
                    chat_id=chat_id,
                    timestamp=datetime.now()
                )
                
                if chat_id not in self.bot_messages:
                    self.bot_messages[chat_id] = []
                
                self.bot_messages[chat_id].append(bot_message)
                asyncio.create_task(self.schedule_message_deletion(bot_message, auto_delete_minutes))
        except Exception as e:
            logger.error(f"Error tracking bot message: {e}")

    async def schedule_message_deletion(self, bot_message: BotMessage, minutes: int):
        """Schedule message deletion after specified minutes"""
        try:
            await asyncio.sleep(minutes * 60)
            await self.delete_message(bot_message.chat_id, bot_message.message_id)
            
            if bot_message.chat_id in self.bot_messages:
                self.bot_messages[bot_message.chat_id] = [
                    msg for msg in self.bot_messages[bot_message.chat_id]
                    if msg.message_id != bot_message.message_id
                ]
        except Exception as e:
            logger.error(f"Error deleting scheduled message: {e}")

    def get_main_menu_keyboard(self):
        """Get main menu inline keyboard"""
        return {
            "inline_keyboard": [
                [
                    {"text": "📝 New Complaint", "callback_data": "new_complaint"},
                    {"text": "📋 Check Status", "callback_data": "check_status"}
                ],
                [
                    {"text": "📞 Contact Info", "callback_data": "contact_info"},
                    {"text": "❓ FAQ", "callback_data": "faq"}
                ]
            ]
        }

    def get_admin_keyboard(self):
        """Get admin inline keyboard"""
        return {
            "inline_keyboard": [
                [
                    {"text": "📋 Complaints", "callback_data": "admin_complaints"},
                    {"text": "🚫 Banned Words", "callback_data": "admin_banned_words"}
                ],
                [
                    {"text": "🤖 Auto Responses", "callback_data": "admin_auto_responses"},
                    {"text": "⚙️ Group Settings", "callback_data": "admin_group_settings"}
                ],
                [
                    {"text": "📊 Statistics", "callback_data": "admin_statistics"}
                ]
            ]
        }

    async def handle_start(self, message: dict):
        """Handle /start command"""
        user = message["from"]
        chat_id = message["chat"]["id"]
        chat_type = message["chat"]["type"]
        user_id = user["id"]

        await self.db.add_user(
            user["id"],
            user.get("username", ""),
            user.get("first_name", ""),
            user.get("last_name", "")
        )

        if chat_type in ["group", "supergroup"]:
            # Bot can respond in groups now
            if await self.is_admin(chat_id, user_id) or user_id == ADMIN_ID:
                admin_group_text = (
                    "🔧 *Admin Group Commands:*\n\n"
                    "/closegroup - Close group for users\n"
                    "/opengroup - Open group for users\n"
                    "/addban <word> - Add banned word\n"
                    "/removeban <word> - Remove banned word\n"
                    "/setautodelete <minutes> - Set auto-delete time\n"
                    "/admin - Show admin panel"
                )
                await self.send_message(chat_id, admin_group_text)
            else:
                # Regular users can also start the bot in group
                welcome_text = (
                    "👋 *Welcome!*\n\n"
                    "I'm your customer support bot. You can:\n"
                    "• Send me a private message for support\n"
                    "• Use commands here if you're an admin\n"
                    "• Follow group rules and guidelines"
                )
                await self.send_message(chat_id, welcome_text)
        
        elif chat_type == "private":
            welcome_text = (
                "👋 *Welcome to our Customer Support Bot!*\n\n"
                "🎯 How can we help you today?\n\n"
                "Please choose an option below or write your complaint/question and we'll get back to you soon!"
            )
            await self.send_message(chat_id, welcome_text, self.get_main_menu_keyboard())

    async def handle_admin_command(self, message: dict):
        """Handle /admin command"""
        user_id = message["from"]["id"]
        chat_id = message["chat"]["id"]
        chat_type = message["chat"]["type"]

        if user_id != ADMIN_ID:
            if chat_type == "private":
                await self.send_message(chat_id, "❌ You don't have admin permissions.")
            return

        if chat_type in ["group", "supergroup"]:
            if not await self.is_admin(chat_id, user_id):
                await self.send_message(chat_id, "❌ You need to be a group admin to use this command.")
                return

        admin_text = "🔧 *Admin Control Panel*\n\nWelcome to the admin dashboard. Choose an option:"
        await self.send_message(chat_id, admin_text, self.get_admin_keyboard())

    async def handle_complaint(self, message: dict):
        """Handle user complaint"""
        user = message["from"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        result = await self.db.add_complaint(
            user["id"],
            text,
            user.get("username", "No username")
        )

        if result and result.data:
            complaint_id = result.data[0]["id"]
            
            confirmation_text = (
                f"✅ *Thank you for your message!*\n\n"
                f"📝 Your complaint has been recorded with ID: *#{complaint_id}*\n\n"
                f"👨‍💼 Our admin will review and respond to you shortly.\n\n"
                f"⏰ Average response time: 2-24 hours"
            )
            await self.send_message(chat_id, confirmation_text)

            admin_text = (
                f"🔔 *New Customer Complaint*\n\n"
                f"👤 User: @{user.get('username', 'No username')} ({user['id']})\n"
                f"📝 Message: {text}\n"
                f"🆔 Complaint ID: #{complaint_id}\n\n"
                f"To reply: `/reply {user['id']} Your response here`"
            )
            await self.send_message(ADMIN_ID, admin_text)

    async def handle_banned_word(self, message: dict):
        """Handle message with banned word"""
        user = message["from"]
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        await self.delete_message(chat_id, message_id)
        await self.db.add_warning(user["id"], "Used banned word")

        warnings = await self.db.get_user_warnings(user["id"])
        warning_count = len(warnings)

        settings = await self.db.get_group_settings()
        max_warnings = settings.get("max_warnings", 3)

        if warning_count >= max_warnings:
            mute_duration = settings.get("mute_duration", 60)
            mute_until = int((datetime.now() + timedelta(minutes=mute_duration)).timestamp())
            
            await self.restrict_chat_member(chat_id, user["id"], mute_until)
            
            mute_text = f"🔇 @{user.get('username', user.get('first_name', 'User'))} has been muted for {mute_duration} minutes due to repeated violations."
            await self.send_message(chat_id, mute_text)
            
            await self.db.clear_user_warnings(user["id"])
        else:
            warning_text = f"⚠️ @{user.get('username', user.get('first_name', 'User'))}, please avoid using banned words. Warning {warning_count}/{max_warnings}"
            await self.send_message(chat_id, warning_text)

    async def check_banned_words(self, text: str) -> bool:
        """Check if message contains banned words"""
        banned_words = await self.db.get_banned_words()
        text_lower = text.lower()
        
        for word_data in banned_words:
            if word_data["word"] in text_lower:
                return True
        return False

    async def check_auto_responses(self, message: dict):
        """Check and send auto responses"""
        text = message.get("text", "").lower()
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        auto_responses = await self.db.get_auto_responses()
        
        for response_data in auto_responses:
            trigger = response_data["trigger"]
            response = response_data["response"]
            
            if trigger in text:
                await self.send_message(chat_id, response, reply_to_message_id=message_id)
                break

    async def handle_admin_group_commands(self, message: dict):
        """Handle admin commands in group"""
        text = message.get("text", "")
        chat_id = message["chat"]["id"]

        if text == "/closegroup":
            await self.db.update_group_settings({"is_closed": True})
            await self.send_message(chat_id, "🔒 Group has been closed. Only admins can send messages.")
        
        elif text == "/opengroup":
            await self.db.update_group_settings({"is_closed": False})
            await self.send_message(chat_id, "🔓 Group has been opened. Users can send messages.")
        
        elif text.startswith("/addban "):
            word = text.split(" ", 1)[1]
            await self.db.add_banned_word(word)
            await self.send_message(chat_id, f"✅ Added \"{word}\" to banned words list.")
        
        elif text.startswith("/removeban "):
            word = text.split(" ", 1)[1]
            await self.db.remove_banned_word(word)
            await self.send_message(chat_id, f"✅ Removed \"{word}\" from banned words list.")
        
        elif text.startswith("/setautodelete "):
            try:
                minutes = int(text.split(" ", 1)[1])
                await self.db.update_group_settings({"auto_delete_minutes": minutes})
                if minutes > 0:
                    await self.send_message(chat_id, f"✅ Bot messages will now be auto-deleted after {minutes} minutes.")
                else:
                    await self.send_message(chat_id, "✅ Auto-delete disabled.")
            except ValueError:
                await self.send_message(chat_id, "❌ Please provide a valid number of minutes.")

    async def handle_callback_query(self, callback_query: dict):
        """Handle callback queries"""
        user_id = callback_query["from"]["id"]
        callback_query_id = callback_query["id"]
        
        # Always answer the callback query first
        await self.answer_callback_query(callback_query_id)
        
        if user_id == ADMIN_ID:
            await self.handle_admin_callback(callback_query)
        else:
            await self.handle_user_callback(callback_query)

    async def handle_user_callback(self, callback_query: dict):
        """Handle user callback queries"""
        data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]

        if data == "new_complaint":
            text = "📝 Please write your complaint or question below:\n\n💡 Be as detailed as possible so we can help you better!"
            await self.edit_message_text(chat_id, message_id, text)
        
        elif data == "contact_info":
            contact_text = (
                "📞 *Contact Information*\n\n"
                "🤖 Bot Support: Available 24/7\n"
                "👨‍💼 Admin: Contact through this bot\n"
                "📧 Email: support@example.com\n"
                "🌐 Website: https://example.com"
            )
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Menu", "callback_data": "back_to_menu"}]
                ]
            }
            await self.edit_message_text(chat_id, message_id, contact_text, back_keyboard)
        
        elif data == "faq":
            faq_text = (
                "❓ *Frequently Asked Questions*\n\n"
                "**Q: How long does it take to get a response?**\n"
                "A: Usually within 2-24 hours.\n\n"
                "**Q: Can I track my complaint?**\n"
                "A: Yes, use the \"Check Status\" button.\n\n"
                "**Q: Is this service free?**\n"
                "A: Yes, our support is completely free!"
            )
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Menu", "callback_data": "back_to_menu"}]
                ]
            }
            await self.edit_message_text(chat_id, message_id, faq_text, back_keyboard)
        
        elif data == "back_to_menu":
            welcome_text = (
                "👋 *Welcome to our Customer Support Bot!*\n\n"
                "🎯 How can we help you today?\n\n"
                "Please choose an option below or write your complaint/question and we'll get back to you soon!"
            )
            await self.edit_message_text(chat_id, message_id, welcome_text, self.get_main_menu_keyboard())

    async def handle_admin_callback(self, callback_query: dict):
        """Handle admin callback queries"""
        data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]

        if data == "admin_statistics":
            # Get statistics
            complaints_stats = await self.db.get_complaints_stats()
            users_count = await self.db.get_users_stats()
            auto_responses_count = await self.db.get_auto_responses_stats()
            banned_words = await self.db.get_banned_words()
            
            stats_text = (
                f"📊 *Bot Statistics*\n\n"
                f"👥 Total Users: {users_count}\n"
                f"📋 Total Complaints: {complaints_stats['total']}\n"
                f"⏳ Pending Complaints: {complaints_stats['pending']}\n"
                f"✅ Resolved Complaints: {complaints_stats['resolved']}\n"
                f"🤖 Auto Responses: {auto_responses_count}\n"
                f"🚫 Banned Words: {len(banned_words)}\n\n"
                f"📈 Resolution Rate: {(complaints_stats['resolved'] / max(complaints_stats['total'], 1) * 100):.1f}%"
            )
            
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Admin Panel", "callback_data": "back_to_admin"}]
                ]
            }
            await self.edit_message_text(chat_id, message_id, stats_text, back_keyboard)
        
        elif data == "admin_group_settings":
            settings = await self.db.get_group_settings()
            settings_text = (
                f"⚙️ *Group Settings*\n\n"
                f"Group Status: {'🔒 Closed' if settings.get('is_closed') else '🔓 Open'}\n"
                f"Max Warnings: {settings.get('max_warnings', 3)}\n"
                f"Mute Duration: {settings.get('mute_duration', 60)} minutes\n"
                f"Auto-delete: {settings.get('auto_delete_minutes', 0)} minutes\n\n"
                f"**Commands:**\n"
                f"`/closegroup` - Close group\n"
                f"`/opengroup` - Open group\n"
                f"`/setautodelete <minutes>` - Set auto-delete time (0 to disable)"
            )
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Admin Panel", "callback_data": "back_to_admin"}]
                ]
            }
            await self.edit_message_text(chat_id, message_id, settings_text, back_keyboard)
        
        elif data == "admin_banned_words":
            banned_words = await self.db.get_banned_words()
            if banned_words:
                words_list = "\n".join([f"{i+1}. {word['word']}" for i, word in enumerate(banned_words)])
                text = f"🚫 *Banned Words Management*\n\nCurrent banned words:\n{words_list}\n\nTo add: `/addban <word>`\nTo remove: `/removeban <word>`"
            else:
                text = "🚫 *Banned Words Management*\n\nNo banned words set.\n\nTo add: `/addban <word>`"
            
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Admin Panel", "callback_data": "back_to_admin"}]
                ]
            }
            await self.edit_message_text(chat_id, message_id, text, back_keyboard)
        
        elif data == "admin_auto_responses":
            auto_responses = await self.db.get_auto_responses()
            if auto_responses:
                responses_list = "\n".join([f"{i+1}. {resp['trigger']} → {resp['response'][:50]}..." for i, resp in enumerate(auto_responses)])
                text = f"🤖 *Auto Responses Management*\n\nCurrent auto responses:\n{responses_list}\n\nTo add: `/addresponse <trigger> | <response>`"
            else:
                text = "🤖 *Auto Responses Management*\n\nNo auto responses set.\n\nTo add: `/addresponse <trigger> | <response>`"
            
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Admin Panel", "callback_data": "back_to_admin"}]
                ]
            }
                        await self.edit_message_text(chat_id, message_id, text, back_keyboard)
        
        elif data == "admin_complaints":
            complaints_stats = await self.db.get_complaints_stats()
            complaints_text = (
                f"📋 *Complaints Management*\n\n"
                f"📊 Total: {complaints_stats['total']}\n"
                f"⏳ Pending: {complaints_stats['pending']}\n"
                f"✅ Resolved: {complaints_stats['resolved']}\n\n"
                f"Use `/reply <user_id> <message>` to respond to complaints"
            )
            
            back_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔙 Back to Admin Panel", "callback_data": "back_to_admin"}]
                ]
            }
            await self.edit_message_text(chat_id, message_id, complaints_text, back_keyboard)
        
        elif data == "back_to_admin":
            admin_text = "🔧 *Admin Control Panel*\n\nWelcome to the admin dashboard. Choose an option:"
            await self.edit_message_text(chat_id, message_id, admin_text, self.get_admin_keyboard())

    async def process_update(self, update: dict):
        """Process incoming update"""
        try:
            if "message" in update:
                message = update["message"]
                text = message.get("text", "")
                chat_type = message["chat"]["type"]
                user_id = message["from"]["id"]
                chat_id = message["chat"]["id"]

                # Handle commands
                if text.startswith("/start"):
                    await self.handle_start(message)
                elif text.startswith("/admin"):
                    await self.handle_admin_command(message)
                elif chat_type == "private":
                    if user_id == ADMIN_ID and text.startswith("/reply "):
                        parts = text.split(" ", 2)
                        if len(parts) >= 3:
                            target_user_id = int(parts[1])
                            reply_text = parts[2]
                            reply_message = f"💬 *Response from Admin:*\n\n{reply_text}\n\nIf you have more questions, feel free to ask!"
                            await self.send_message(target_user_id, reply_message)
                            await self.send_message(ADMIN_ID, "✅ Reply sent successfully!")
                    elif user_id == ADMIN_ID and text.startswith("/addban "):
                        word = text.split(" ", 1)[1]
                        await self.db.add_banned_word(word)
                        await self.send_message(chat_id, f"✅ Added \"{word}\" to banned words list.")
                    elif user_id == ADMIN_ID and text.startswith("/removeban "):
                        word = text.split(" ", 1)[1]
                        await self.db.remove_banned_word(word)
                        await self.send_message(chat_id, f"✅ Removed \"{word}\" from banned words list.")
                    elif user_id == ADMIN_ID and text.startswith("/addresponse "):
                        try:
                            content = text.split(" ", 1)[1]
                            trigger, response = content.split(" | ", 1)
                            await self.db.add_auto_response(trigger.strip(), response.strip())
                            await self.send_message(chat_id, f"✅ Added auto response for \"{trigger}\"")
                        except ValueError:
                            await self.send_message(chat_id, "❌ Format: /addresponse <trigger> | <response>")
                    else:
                        await self.handle_complaint(message)
                elif GROUP_ID and str(chat_id) == GROUP_ID:
                    # Handle group messages
                    if user_id == ADMIN_ID or await self.is_admin(chat_id, user_id):
                        await self.handle_admin_group_commands(message)
                    else:
                        settings = await self.db.get_group_settings()
                        if settings.get("is_closed"):
                            await self.delete_message(chat_id, message["message_id"])
                            warning_msg = await self.send_message(chat_id, "🔒 Group is currently closed. Messages are not allowed.")
                            # Auto-delete warning message after 5 seconds
                            if warning_msg and warning_msg.get("ok"):
                                asyncio.create_task(self.auto_delete_warning(chat_id, warning_msg["result"]["message_id"]))
                            return

                        if await self.check_banned_words(text):
                            await self.handle_banned_word(message)
                            return

                        await self.check_auto_responses(message)
                elif chat_type in ["group", "supergroup"]:
                    # Handle other groups (not the main support group)
                    if text.startswith("/start") or text.startswith("/admin"):
                        # Allow bot commands in any group
                        if text.startswith("/start"):
                            await self.handle_start(message)
                        elif text.startswith("/admin"):
                            await self.handle_admin_command(message)
                    elif user_id == ADMIN_ID or await self.is_admin(chat_id, user_id):
                        # Allow admin commands in any group for admins
                        await self.handle_admin_group_commands(message)

            elif "callback_query" in update:
                await self.handle_callback_query(update["callback_query"])

        except Exception as e:
            logger.error(f"Error processing update: {e}")

    async def auto_delete_warning(self, chat_id: int, message_id: int):
        """Auto-delete warning message after 5 seconds"""
        try:
            await asyncio.sleep(5)
            await self.delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"Error auto-deleting warning message: {e}")

# Initialize bot
bot = TelegramBot(BOT_TOKEN)

@app.post("/api/webhook")
async def webhook(request: Request):
    """Handle webhook updates"""
    try:
        update = await request.json()
        logger.info(f"Received update: {update.get('update_id', 'unknown')}")
        await bot.process_update(update)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse({"status": "error", "message": str(e)})

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "OK", "timestamp": datetime.now().isoformat()}

@app.get("/api/setwebhook")
async def set_webhook(request: Request):
    """Set webhook URL"""
    try:
        webhook_url = f"{request.url.scheme}://{request.headers['host']}/api/webhook"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url}
            )
            result = response.json()
            
            if result.get("ok"):
                return {"success": True, "webhook": webhook_url}
            else:
                return {"success": False, "error": result.get("description")}
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
