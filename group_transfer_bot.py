#!/usr/bin/env python3
"""
GroupTransferBot - Telegram Bot for transferring members between groups/channels
Features:
- Admin-only access with proper authentication
- Member scraping and transfer functionality
- Admin management commands
- Proper error handling and rate limiting
"""

import asyncio
import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import time

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserPrivacyRestrictedError
from telethon.tl.types import User, Chat, Channel
from telethon.tl.functions.channels import InviteToChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "bot_session")

# Admin configuration
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CONTACT_ADMIN_USERNAME = "@thegodoftgbot"

# Rate limiting configuration
TRANSFER_DELAY = 10  # seconds between invites
MAX_RETRIES = 3
FLOOD_WAIT_THRESHOLD = 3600  # 1 hour max wait

class TransferStates(StatesGroup):
    waiting_source_id = State()
    waiting_target_id = State()
    confirming_transfer = State()

class GroupTransferBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.client: Optional[TelegramClient] = None
        self.transfer_tasks: Dict[int, asyncio.Task] = {}
        self.db_path = "bot_data.db"
        self.init_database()
        self.setup_handlers()
        
    def init_database(self):
        """Initialize SQLite database for storing bot data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Admins table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Transfer sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfer_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                source_chat_id TEXT,
                target_chat_id TEXT,
                status TEXT DEFAULT 'pending',
                total_members INTEGER DEFAULT 0,
                transferred_members INTEGER DEFAULT 0,
                failed_members INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        
        # Add default admin if ADMIN_IDS is provided
        for admin_id in ADMIN_IDS:
            cursor.execute('''
                INSERT OR IGNORE INTO admins (user_id, username, first_name, added_by)
                VALUES (?, ?, ?, ?)
            ''', (admin_id, "default_admin", "Default Admin", admin_id))
        
        conn.commit()
        conn.close()
        
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
        
    def add_admin(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None, added_by: Optional[int] = None):
        """Add new admin to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO admins (user_id, username, first_name, added_by)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, added_by))
        conn.commit()
        conn.close()
        
    def remove_admin(self, user_id: int):
        """Remove admin from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
    def get_all_admins(self) -> List[Dict]:
        """Get all admins from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, added_at 
            FROM admins ORDER BY added_at
        ''')
        admins = []
        for row in cursor.fetchall():
            admins.append({
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'added_at': row[3]
            })
        conn.close()
        return admins
        
    def admin_only_keyboard(self):
        """Create keyboard with contact admin button for non-admins"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Contact Admin", url=f"https://t.me/{CONTACT_ADMIN_USERNAME.lstrip('@')}")]
        ])
        return keyboard
        
    def transfer_control_keyboard(self):
        """Create keyboard for transfer control"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 Fetch from", callback_data="fetch_from"),
                InlineKeyboardButton(text="📤 Push to", callback_data="push_to")
            ],
            [InlineKeyboardButton(text="✅ Done", callback_data="done_setup")]
        ])
        return keyboard
        
    async def init_telethon_client(self):
        """Initialize Telethon client for user operations"""
        if not self.client:
            self.client = TelegramClient(SESSION_STRING, API_ID, API_HASH)
            await self.client.start()
            logger.info("Telethon client initialized")
            
    def setup_handlers(self):
        """Setup all bot handlers"""
        
        @self.dp.message(CommandStart())
        async def start_command(message: Message):
            """Handle /start command"""
            if not message.from_user:
                return
                
            welcome_text = (
                "🤖 **Welcome to GroupTransferBot!**\n\n"
                "Here are the available commands:\n"
                "• `/scrapemembers` - Transfer members between groups\n"
                "• `/promote <uid>` - Promote user to admin\n"
                "• `/remove <uid>` - Remove user from admin\n"
                "• `/adminlist` - Show current admins\n"
                "• `/refresh` - Refresh/reboot the bot\n\n"
                "⚠️ Note: All commands are admin-only."
            )
            
            if self.is_admin(message.from_user.id):
                await message.reply(welcome_text, parse_mode="Markdown")
            else:
                await message.reply(
                    "🤖 Welcome to GroupTransferBot!\n\n"
                    "This bot is for admins only. Please contact admin to use this bot.",
                    reply_markup=self.admin_only_keyboard()
                )
                
        @self.dp.message(Command("scrapemembers"))
        async def scrape_members_command(message: Message, state: FSMContext):
            """Handle /scrapemembers command"""
            if not message.from_user:
                return
                
            if not self.is_admin(message.from_user.id):
                await message.reply(
                    "❌ This command is for admins only.",
                    reply_markup=self.admin_only_keyboard()
                )
                return
                
            await state.clear()
            await state.set_data({
                'source_chat_id': None,
                'target_chat_id': None,
                'admin_id': message.from_user.id
            })
            
            text = (
                "🔄 **Member Transfer Setup**\n\n"
                "Click the buttons below to configure the transfer:\n"
                "• **Fetch from**: Source group/channel\n"
                "• **Push to**: Target group/channel\n\n"
                "Then click **Done** to start the transfer."
            )
            
            await message.reply(text, reply_markup=self.transfer_control_keyboard(), parse_mode="Markdown")
            
        @self.dp.callback_query(F.data == "fetch_from")
        async def fetch_from_callback(callback: CallbackQuery, state: FSMContext):
            """Handle fetch from button"""
            if not callback.message:
                return
                
            await state.set_state(TransferStates.waiting_source_id)
            await callback.message.edit_text(
                "📥 **Set Source Group**\n\n"
                "Please send the chat ID of the group/channel you want to fetch members FROM.\n"
                "Example: `-1001234567890` or `@channelname`",
                parse_mode="Markdown"
            )
            await callback.answer()
            
        @self.dp.callback_query(F.data == "push_to")
        async def push_to_callback(callback: CallbackQuery, state: FSMContext):
            """Handle push to button"""
            if not callback.message:
                return
                
            await state.set_state(TransferStates.waiting_target_id)
            await callback.message.edit_text(
                "📤 **Set Target Group**\n\n"
                "Please send the chat ID of the group/channel you want to push members TO.\n"
                "Example: `-1001234567890` or `@channelname`",
                parse_mode="Markdown"
            )
            await callback.answer()
            
        @self.dp.message(TransferStates.waiting_source_id)
        async def handle_source_id(message: Message, state: FSMContext):
            """Handle source chat ID input"""
            if not message.text:
                return
                
            data = await state.get_data()
            data['source_chat_id'] = message.text.strip()
            await state.set_data(data)
            
            await message.reply(
                f"✅ Source set to: `{message.text.strip()}`\n\n"
                "Now configure the target using the buttons above.",
                reply_markup=self.transfer_control_keyboard(),
                parse_mode="Markdown"
            )
            await state.clear()
            
        @self.dp.message(TransferStates.waiting_target_id)
        async def handle_target_id(message: Message, state: FSMContext):
            """Handle target chat ID input"""
            if not message.text:
                return
                
            data = await state.get_data()
            data['target_chat_id'] = message.text.strip()
            await state.set_data(data)
            
            await message.reply(
                f"✅ Target set to: `{message.text.strip()}`\n\n"
                "Click Done when ready to start the transfer.",
                reply_markup=self.transfer_control_keyboard(),
                parse_mode="Markdown"
            )
            
        @self.dp.callback_query(F.data == "done_setup")
        async def done_setup_callback(callback: CallbackQuery, state: FSMContext):
        """Handle Done button click — start transfer if both ids exist"""
            await callback.answer()  # acknowledge click (non-alert)

            data = await state.get_data()
            source_id = data.get("source_chat_id")
            target_id = data.get("target_chat_id")
            admin_id = data.get("admin_id")  # if you're saving admin earlier

            if not source_id or not target_id:
            await callback.answer("❌ Please set both SOURCE and TARGET group IDs first!", show_alert=True)
            return

          # Edit message so user knows transfer started
          if callback.message:
              await callback.message.edit_text(
              "🚀 Starting Member Transfer...\n\n"
              f"From: `{source_id}`\nTo: `{target_id}`\n\n"
              "Check logs for progress.",
              parse_mode="Markdown"
              )

            # Start the transfer in background so the request returns quickly
            # ensure transfer_members is the function that does the heavy work
            task = asyncio.create_task(
            self.transfer_members(source_id, target_id, callback.message.chat.id, admin_id)
          )

          # NOW clear the state (safe: transfer already started)
            await state.clear()
           
        @self.dp.message(Command("promote"))
        async def promote_command(message: Message):
            """Handle /promote command"""
            if not message.from_user or not message.text:
                return
                
            if not self.is_admin(message.from_user.id):
                await message.reply(
                    "❌ This command is for admins only.",
                    reply_markup=self.admin_only_keyboard()
                )
                return
                
            try:
                parts = message.text.split()
                if len(parts) != 2:
                    await message.reply("❌ Usage: `/promote <user_id>`", parse_mode="Markdown")
                    return
                    
                user_id = int(parts[1])
                
                # Try to get user info
                try:
                    user_info = await self.bot.get_chat(user_id)
                    username = user_info.username or "N/A"
                    first_name = user_info.first_name or "N/A"
                except:
                    username = "N/A"
                    first_name = "N/A"
                    
                self.add_admin(user_id, username, first_name, message.from_user.id)
                
                await message.reply(
                    f"✅ **User promoted to admin**\n\n"
                    f"**User ID:** `{user_id}`\n"
                    f"**Username:** @{username}\n"
                    f"**Name:** {first_name}",
                    parse_mode="Markdown"
                )
                
            except ValueError:
                await message.reply("❌ Invalid user ID. Please provide a numeric user ID.")
            except Exception as e:
                await message.reply(f"❌ Error promoting user: {str(e)}")
                
        @self.dp.message(Command("remove"))
        async def remove_command(message: Message):
            """Handle /remove command"""
            if not message.from_user or not message.text:
                return
                
            if not self.is_admin(message.from_user.id):
                await message.reply(
                    "❌ This command is for admins only.",
                    reply_markup=self.admin_only_keyboard()
                )
                return
                
            try:
                parts = message.text.split()
                if len(parts) != 2:
                    await message.reply("❌ Usage: `/remove <user_id>`", parse_mode="Markdown")
                    return
                    
                user_id = int(parts[1])
                
                if not self.is_admin(user_id):
                    await message.reply("❌ User is not an admin.")
                    return
                    
                self.remove_admin(user_id)
                
                await message.reply(
                    f"✅ **Admin removed**\n\n"
                    f"**User ID:** `{user_id}`",
                    parse_mode="Markdown"
                )
                
            except ValueError:
                await message.reply("❌ Invalid user ID. Please provide a numeric user ID.")
            except Exception as e:
                await message.reply(f"❌ Error removing admin: {str(e)}")
                
        @self.dp.message(Command("adminlist"))
        async def adminlist_command(message: Message):
            """Handle /adminlist command"""
            if not message.from_user:
                return
                
            if not self.is_admin(message.from_user.id):
                await message.reply(
                    "❌ This command is for admins only.",
                    reply_markup=self.admin_only_keyboard()
                )
                return
                
            admins = self.get_all_admins()
            
            if not admins:
                await message.reply("❌ No admins found.")
                return
                
            text = "👥 **Current Admins:**\n\n"
            
            for i, admin in enumerate(admins, 1):
                username = admin['username'] or "N/A"
                first_name = admin['first_name'] or "N/A"
                text += f"{i}. User ID: `{admin['user_id']}`\n"
                text += f"   Username: @{username}\n"
                text += f"   Name: {first_name}\n"
                text += f"   Added: {admin['added_at']}\n\n"
                
            await message.reply(text, parse_mode="Markdown")
            
        @self.dp.message(Command("refresh"))
        async def refresh_command(message: Message):
            """Handle /refresh command"""
            if not message.from_user:
                return
                
            if not self.is_admin(message.from_user.id):
                await message.reply(
                    "❌ This command is for admins only.",
                    reply_markup=self.admin_only_keyboard()
                )
                return
                
            await message.reply("🔄 **Bot refreshed successfully!**\n\nAll systems operational.", parse_mode="Markdown")
            
        # Handle non-admin attempts for other commands
        @self.dp.message()
        async def handle_unknown(message: Message):
            """Handle unknown commands from non-admins"""
            if not message.from_user or not message.text:
                return
                
            if message.text.startswith('/'):
                if not self.is_admin(message.from_user.id):
                    await message.reply(
                        "❌ This command is for admins only.",
                        reply_markup=self.admin_only_keyboard()
                    )
                    
    async def get_chat_members(self, chat_id: str) -> List[Dict]:
        """Get all members from a chat using Telethon"""
        await self.init_telethon_client()
        
        if not self.client:
            raise Exception("Failed to initialize Telethon client")
        
        try:
            # Get the chat entity
            entity = await self.client.get_entity(chat_id)
            title = getattr(entity, 'title', chat_id)
            logger.info(f"Getting members from chat: {title}")
            
            members = []
            offset = 0
            limit = 100
            
            while True:
                try:
                    participants = await self.client(GetParticipantsRequest(
                        entity, ChannelParticipantsSearch(''), offset, limit, hash=0
                    ))
                    
                    if not hasattr(participants, 'users') or not participants.users:
                        break
                        
                    for user in participants.users:
                        if isinstance(user, User) and not user.bot and not user.deleted:
                            members.append({
                                'id': user.id,
                                'username': user.username,
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                                'access_hash': user.access_hash
                            })
                    
                    offset += len(participants.users)
                    
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except FloodWaitError as e:
                    logger.warning(f"Flood wait: {e.seconds} seconds")
                    if e.seconds > FLOOD_WAIT_THRESHOLD:
                        raise Exception(f"Flood wait too long: {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)
                    
            logger.info(f"Found {len(members)} members")
            return members
            
        except Exception as e:
            logger.error(f"Error getting chat members: {str(e)}")
            raise
            
    async def transfer_members(self, source_chat_id: str, target_chat_id: str, notification_chat_id: int, admin_id: int):
        """Transfer members from source to target chat"""
        try:
            await self.init_telethon_client()
            
            if not self.client:
                raise Exception("Failed to initialize Telethon client")
            
            # Notify start
            await self.bot.send_message(
                notification_chat_id,
                "🔍 **Fetching members from source group...**",
                parse_mode="Markdown"
            )
            
            # Get members from source
            members = await self.get_chat_members(source_chat_id)
            
            if not members:
                await self.bot.send_message(
                    notification_chat_id,
                    "❌ **No members found in source group.**",
                    parse_mode="Markdown"
                )
                return
                
            await self.bot.send_message(
                notification_chat_id,
                f"📊 **Found {len(members)} members**\n\n🚀 Starting transfer process...",
                parse_mode="Markdown"
            )
            
            # Get target entity
            target_entity = await self.client.get_entity(target_chat_id)
            
            transferred = 0
            failed = 0
            
            # Transfer members one by one
            for i, member in enumerate(members):
                try:
                    # Create user entity
                    user = await self.client.get_entity(member['id'])
                    
                    # Invite user to target group
                    await self.client(InviteToChannelRequest(
                        target_entity,
                        [user]
                    ))
                    
                    transferred += 1
                    logger.info(f"Transferred user {member['id']} ({member.get('username', 'N/A')})")
                    
                    # Send progress update every 10 transfers
                    if (i + 1) % 10 == 0:
                        await self.bot.send_message(
                            notification_chat_id,
                            f"📊 **Progress Update**\n\n"
                            f"✅ Transferred: {transferred}\n"
                            f"❌ Failed: {failed}\n"
                            f"📈 Progress: {i + 1}/{len(members)}",
                            parse_mode="Markdown"
                        )
                    
                except FloodWaitError as e:
                    logger.warning(f"Flood wait for user {member['id']}: {e.seconds} seconds")
                    if e.seconds > FLOOD_WAIT_THRESHOLD:
                        failed += 1
                        continue
                    await asyncio.sleep(e.seconds)
                    # Retry the same user
                    continue
                    
                except (ChatAdminRequiredError, UserPrivacyRestrictedError) as e:
                    logger.warning(f"Cannot invite user {member['id']}: {str(e)}")
                    failed += 1
                    
                except Exception as e:
                    logger.error(f"Error transferring user {member['id']}: {str(e)}")
                    failed += 1
                    
                # Rate limiting between invites
                await asyncio.sleep(TRANSFER_DELAY)
                
            # Final report
            completion_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            final_message = (
                f"🎉 **Transfer Complete!**\n\n"
                f"📊 **Final Statistics:**\n"
                f"✅ Successfully transferred: {transferred}\n"
                f"❌ Failed transfers: {failed}\n"
                f"📈 Total processed: {len(members)}\n"
                f"⏰ Completed at: {completion_time}\n\n"
                f"⚠️ **Note:** Failed transfers may be due to user privacy settings or admin restrictions."
            )
            
            await self.bot.send_message(
                notification_chat_id,
                final_message,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            error_message = (
                f"❌ **Transfer Failed**\n\n"
                f"**Error:** {str(e)}\n\n"
                f"Please check the chat IDs and try again."
            )
            
            await self.bot.send_message(
                notification_chat_id,
                error_message,
                parse_mode="Markdown"
            )
            
        finally:
            # Clean up task reference
            if notification_chat_id in self.transfer_tasks:
                del self.transfer_tasks[notification_chat_id]
                
    async def run(self):
        """Start the bot"""
        logger.info("Starting GroupTransferBot...")
        
        # Validate configuration
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is required")
        if not API_ID or not API_HASH:
            raise ValueError("API_ID and API_HASH environment variables are required")
            
        try:
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise
        finally:
            if self.client:
                await self.client.disconnect()

async def main():
    """Main function"""
    bot = GroupTransferBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
