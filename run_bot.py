#!/usr/bin/env python3
"""
Simple runner script for GroupTransferBot with FastAPI + Render fixes
"""

import subprocess
import sys
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

# ----------------------------
# FastAPI Lifespan (startup/shutdown)
# ----------------------------
async def on_startup_handler():
    print("🚀 Bot starting up...")

async def on_shutdown_handler():
    print("🛑 Bot shutting down...")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await on_startup_handler()
    yield
    await on_shutdown_handler()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "message": "GroupTransferBot is running ✅"}

# ----------------------------
# Main runner
# ----------------------------
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
        # Run the bot script as subprocess
        subprocess.Popen([sys.executable, "group_transfer_bot.py"])

        # Start FastAPI server (Render requires this)
        port = int(os.environ.get("PORT", 10000))
        uvicorn.run("run_bot:app", host="0.0.0.0", port=port, reload=False)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == "__main__":
    main()
