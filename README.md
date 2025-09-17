# GroupTransferBot 🤖

A powerful Telegram bot for transferring members between groups and channels with admin-only access control.

## 🚀 Features

- **Admin-only access** with proper authentication system
- **Member scraping** and bulk transfer between groups/channels
- **Admin management commands** (promote/remove admins)
- **Rate limiting** to prevent Telegram API limits
- **Progress tracking** with real-time updates
- **Error handling** with detailed logging
- **Contact admin button** for non-authorized users

## 📋 Commands

### Admin Commands
- `/start` - Welcome message and command list
- `/scrapemembers` - Transfer members between groups (interactive setup)
- `/promote <user_id>` - Promote user to admin
- `/remove <user_id>` - Remove user from admin
- `/adminlist` - Show current admin list
- `/refresh` - Refresh/reboot the bot

### Non-Admin Behavior
Non-admin users will see a "Contact Admin" button that redirects to `@thegodoftgbot` when trying to use restricted commands.

## 🔧 Setup

### Required Environment Variables
- `BOT_TOKEN` - Get from @BotFather on Telegram
- `API_ID` - Get from https://my.telegram.org
- `API_HASH` - Get from https://my.telegram.org  
- `ADMIN_IDS` - Comma-separated admin user IDs (e.g., "123456789,987654321")
- `SESSION_STRING` - (Optional) Telethon session name

### Installation
```bash
pip install aiogram telethon
```

### Running the Bot
```bash
python3 group_transfer_bot.py
# or
python3 run_bot.py
```

## 💡 How to Use Member Transfer

1. Use `/scrapemembers` command
2. Click "📥 Fetch from" and enter source group ID (e.g., `-1001234567890`)
3. Click "📤 Push to" and enter target group ID
4. Click "✅ Done" to start the transfer
5. Wait 5-10 minutes for completion with progress updates

## ⚠️ Important Notes

- Bot must be added as admin to both source and target groups
- Member transfer requires both Bot API (aiogram) and User API (Telethon)
- Rate limiting is enforced (10 seconds between invites) to prevent bans
- Some members may fail to transfer due to privacy settings
- Always test with small groups first

## 🛡️ Security Features

- Admin-only command access
- Secure secret management
- SQLite database for admin storage  
- Proper error handling and logging
- Rate limiting to prevent API abuse

## 📊 Transfer Statistics

The bot provides detailed statistics after each transfer:
- ✅ Successfully transferred members
- ❌ Failed transfers (with reasons)
- 📈 Total members processed
- ⏰ Completion timestamp

## 🔗 Contact

For support or admin access, contact: @thegodoftgbot

---

**Note**: This bot complies with Telegram's Terms of Service. Use responsibly and respect user privacy.