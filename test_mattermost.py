#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal Mattermost test for CoPaw integration"""

import os
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from mattermostdriver import Driver
except ImportError:
    print("❌ mattermostdriver not installed!")
    print("   Install with: pip install mattermostdriver")
    sys.exit(1)

try:
    from copaw.config import load_config, get_config_path
except ImportError:
    print("⚠️  CoPaw config module not found")
    def get_config_path():
        return Path.home() / ".copaw" / "config.json"
    def load_config(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)


def get_mattermost_config():
    """Get Mattermost configuration"""
    config_path = get_config_path()
    
    if not config_path.exists():
        print("❌ No config file found. Run 'copaw channels config' first.")
        return None
    
    try:
        config = load_config(config_path)
        
        # Handle both object and dict formats
        if hasattr(config, 'channels') and hasattr(config.channels, 'mattermost'):
            mm = config.channels.mattermost
            return {
                'url': getattr(mm, 'mattermost_url', ''),
                'token': getattr(mm, 'bot_token', ''),
                'team_id': getattr(mm, 'team_id', ''),
            }
        elif isinstance(config, dict) and 'channels' in config and 'mattermost' in config['channels']:
            mm = config['channels']['mattermost']
            return {
                'url': mm.get('mattermost_url', ''),
                'token': mm.get('bot_token', ''),
                'team_id': mm.get('team_id', ''),
            }
        else:
            print("❌ Mattermost not configured")
            return None
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return None


def test_mattermost_connection():
    """Test Mattermost connection"""
    config = get_mattermost_config()
    if not config:
        return False
    
    # Check required fields
    if not all([config['url'], config['token'], config['team_id']]):
        print("❌ Configuration incomplete")
        return False
    
    try:
        # Parse URL
        from urllib.parse import urlparse
        parsed = urlparse(config['url'])
        scheme = parsed.scheme or 'http'
        host = parsed.netloc.split(':')[0] if parsed.netloc else 'localhost'
        
        # Auto-detect port
        if ':' in parsed.netloc:
            port = int(parsed.netloc.split(':')[1])
        else:
            port = 443 if scheme == 'https' else 80
        
        # Create driver
        options = {
            'url': host,
            'token': config['token'],
            'scheme': scheme,
            'port': port,
            'basepath': '/api/v4',
            'verify': True,
            'timeout': 30,
        }
        
        driver = Driver(options)
        driver.login()
        
        # Get bot info
        me = getattr(driver.client, 'user_id', None) or getattr(driver.client, 'userid', None)
        if not me:
            me_response = driver.client.get('/users/me')
            me = me_response.get('id')
        
        bot_info = driver.users.get_user(me)
        
        print(f"✅ Connected to Mattermost!")
        print(f"   Bot: {bot_info.get('username', 'N/A')}")
        print(f"   Team ID: {config['team_id']}")
        print(f"   Server: {config['url']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def main():
    """Main function"""
    print("🧪 Mattermost Connection Test")
    print("=" * 50)
    
    result = test_mattermost_connection()
    
    if result:
        print("\n✅ SUCCESS: Mattermost is properly configured and ready to use!")
        print("\nNext steps:")
        print("1. Start CoPaw: copaw app")
        print("2. In Mattermost, send: @copaw-bot hello")
        print("3. Check if you receive a reply")
    else:
        print("\n❌ FAILED: Check your configuration and try again.")
        print("\nRun: copaw channels config")


if __name__ == '__main__':
    main()