#!/usr/bin/env python3
"""
Simple runner script for GroupTransferBot
"""

import subprocess
import sys

def main():
    """Run the GroupTransferBot"""
    print("🤖 Starting GroupTransferBot...")
    print("📋 Make sure you have set all required environment variables:")
    print("   - BOT_TOKEN")
    print("   - API_ID") 
    print("   - API_HASH")
    print("   - ADMIN_IDS")
    print("   - SESSION_STRING (optional)")
    print()
    
    try:
        subprocess.run([sys.executable, "group_transfer_bot.py"], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == "__main__":
    main()