#!/usr/bin/env python3
"""
Test Telegram Bot Connection
Run this after setting up your bot credentials.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.telegram_bot import init_telegram

def main():
    # Get credentials from environment
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        print("\nSet it with:")
        print("  export TELEGRAM_BOT_TOKEN='your_token_here'")
        return False
    
    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID not set!")
        print("\nSet it with:")
        print("  export TELEGRAM_CHAT_ID='your_chat_id_here'")
        return False
    
    print(f"Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    print(f"Chat ID: {chat_id}")
    print("\nTesting connection...")
    
    # Initialize and test
    notifier = init_telegram(bot_token=bot_token, chat_id=chat_id)
    
    if notifier.test_connection():
        print("\n✅ SUCCESS! Check your Telegram for the test message.")
        print("\nTelegram notifications are now active!")
        print("You'll receive alerts when signals are detected.")
        return True
    else:
        print("\n❌ FAILED! Check your credentials.")
        print("\nTroubleshooting:")
        print("1. Make sure the bot token is correct")
        print("2. Make sure you've started a chat with your bot")
        print("3. Make sure the chat ID is correct")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
