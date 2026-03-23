#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test script to verify Mattermost channel registration"""
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("Python path:", sys.path)
print("Current directory:", os.getcwd())

try:
    from copaw.app.channels.registry import get_channel_registry, BUILTIN_CHANNEL_KEYS
    print("✓ Imported registry module")
except Exception as e:
    print(f"✗ Failed to import registry module: {e}")
    sys.exit(1)

try:
    from copaw.cli.channels_cmd import _ALL_CHANNEL_NAMES, _ALL_CHANNEL_CONFIGURATORS
    print("✓ Imported channels_cmd module")
except Exception as e:
    print(f"✗ Failed to import channels_cmd module: {e}")
    sys.exit(1)

def test_mattermost_registration():
    """Test Mattermost channel registration"""
    print("\nTesting Mattermost channel registration...")
    
    # Test 1: Check if mattermost is in built-in channel keys
    print("\n1. Checking if mattermost is in BUILTIN_CHANNEL_KEYS:")
    print(f"   BUILTIN_CHANNEL_KEYS: {list(BUILTIN_CHANNEL_KEYS)}")
    if 'mattermost' in BUILTIN_CHANNEL_KEYS:
        print("   ✓ mattermost is in BUILTIN_CHANNEL_KEYS")
    else:
        print("   ✗ mattermost is NOT in BUILTIN_CHANNEL_KEYS")
    
    # Test 2: Check if mattermost is in channel names
    print("\n2. Checking if mattermost is in channel names:")
    print(f"   Channel names: {list(_ALL_CHANNEL_NAMES.keys())}")
    if 'mattermost' in _ALL_CHANNEL_NAMES:
        print(f"   ✓ mattermost is in channel names: {_ALL_CHANNEL_NAMES['mattermost']}")
    else:
        print("   ✗ mattermost is NOT in channel names")
    
    # Test 3: Check if mattermost has a configurator
    print("\n3. Checking if mattermost has a configurator:")
    print(f"   Configurators: {list(_ALL_CHANNEL_CONFIGURATORS.keys())}")
    if 'mattermost' in _ALL_CHANNEL_CONFIGURATORS:
        print(f"   ✓ mattermost has a configurator: {_ALL_CHANNEL_CONFIGURATORS['mattermost'][0]}")
    else:
        print("   ✗ mattermost does NOT have a configurator")
    
    # Test 4: Check if mattermost is in the channel registry
    print("\n4. Checking if mattermost is in the channel registry:")
    try:
        registry = get_channel_registry()
        print(f"   Registry keys: {list(registry.keys())}")
        if 'mattermost' in registry:
            print(f"   ✓ mattermost is in the channel registry: {registry['mattermost'].__name__}")
        else:
            print("   ✗ mattermost is NOT in the channel registry")
    except Exception as e:
        print(f"   ✗ Failed to get channel registry: {e}")
    
    # Test 5: Try to import MattermostChannel
    print("\n5. Trying to import MattermostChannel:")
    try:
        from copaw.app.channels.mattermost import MattermostChannel
        print(f"   ✓ MattermostChannel imported successfully: {MattermostChannel}")
    except Exception as e:
        print(f"   ✗ Failed to import MattermostChannel: {e}")
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_mattermost_registration()
