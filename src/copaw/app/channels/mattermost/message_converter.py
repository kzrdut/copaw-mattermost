# -*- coding: utf-8 -*-
"""
Mattermost Message Converter Module

This module handles message parsing and conversion between Mattermost's
message format and CoPaw's internal message format.

Supported message types:
- Posted messages (channel/direct/group messages)
- Ephemeral messages
- Reactions
- Typing indicators
- User status changes
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MattermostMessage:
    """Parsed Mattermost message structure."""
    message_id: str
    channel_id: str
    user_id: str
    username: str
    content: str
    message_type: str  # "post", "ephemeral", etc.
    timestamp: int
    raw_data: Dict[str, Any]


class MattermostMessageConverter:
    """
    Converter for Mattermost messages to CoPaw format.
    
    Handles:
    - Parsing Mattermost WebSocket events
    - Extracting message content and metadata
    - Converting to CoPaw's AgentRequest format
    - Converting CoPaw responses to Mattermost format
    """

    SUPPORTED_MESSAGE_TYPES = {"posted", "ephemeral_message"}
    SKIP_BOT_MESSAGES = True

    def __init__(self, bot_user_id: Optional[str] = None):
        self.bot_user_id = bot_user_id
        self._user_cache: Dict[str, Dict[str, Any]] = {}

    def parse_post_event(self, event_data: Dict[str, Any]) -> Optional[MattermostMessage]:
        """
        Parse a 'posted' event from Mattermost WebSocket.
        
        Args:
            event_data: The raw event data from WebSocket
            
        Returns:
            MattermostMessage if parsing successful, None otherwise
        """
        try:
            data = event_data.get("data", {})
            broadcast = event_data.get("broadcast", {})
            
            # Parse post data
            post_data = data.get("post", "{}")
            if isinstance(post_data, str):
                try:
                    post = json.loads(post_data)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse post data: {post_data}")
                    return None
            else:
                post = post_data
            
            if not post:
                logger.warning("Empty post data")
                return None
            
            message_id = post.get("id", "")
            channel_id = post.get("channel_id", "")
            user_id = post.get("user_id", "")
            content = post.get("message", "")
            timestamp = post.get("create_at", 0)
            message_type = post.get("type", "post")
            
            # Skip system messages
            if message_type.startswith("system_"):
                logger.debug(f"Skipping system message: {message_type}")
                return None
            
            # Skip bot messages if configured
            if self.SKIP_BOT_MESSAGES and post.get("props", {}).get("from_bot", False):
                logger.debug("Skipping bot message")
                return None
            
            # Get username from sender_name or cache
            username = post.get("props", {}).get("sender_name", user_id)
            
            # Try to get user info if we have user_id
            if user_id and user_id != "0" and user_id != self.bot_user_id:
                # Username might be in the event data
                username = data.get("sender_name", username)
            
            return MattermostMessage(
                message_id=message_id,
                channel_id=channel_id,
                user_id=user_id,
                username=username,
                content=content,
                message_type=message_type,
                timestamp=timestamp,
                raw_data=event_data,
            )
            
        except Exception as e:
            logger.error(f"Error parsing post event: {e}")
            return None

    def parse_ephemeral_event(self, event_data: Dict[str, Any]) -> Optional[MattermostMessage]:
        """Parse an ephemeral message event."""
        try:
            data = event_data.get("data", {})
            
            post_data = data.get("post", "{}")
            if isinstance(post_data, str):
                try:
                    post = json.loads(post_data)
                except json.JSONDecodeError:
                    return None
            else:
                post = post_data
            
            return MattermostMessage(
                message_id=post.get("id", ""),
                channel_id=post.get("channel_id", ""),
                user_id=data.get("user_id", ""),
                username=data.get("user_id", ""),
                content=post.get("message", ""),
                message_type="ephemeral",
                timestamp=post.get("create_at", 0),
                raw_data=event_data,
            )
        except Exception as e:
            logger.error(f"Error parsing ephemeral event: {e}")
            return None

    def convert_to_native_payload(
        self,
        message: MattermostMessage,
    ) -> Dict[str, Any]:
        """
        Convert MattermostMessage to CoPaw's native payload format.
        
        Args:
            message: Parsed MattermostMessage
            
        Returns:
            Dictionary with CoPaw message format
        """
        return {
            "channel_id": "mattermost",
            "sender_id": message.username or message.user_id,
            "user_id": message.user_id,
            "content_parts": [
                {
                    "type": "text",
                    "text": message.content,
                }
            ],
            "meta": {
                "message_id": message.message_id,
                "channel_id": message.channel_id,
                "user_id": message.user_id,
                "username": message.username,
                "timestamp": message.timestamp,
                "message_type": message.message_type,
            },
        }

    def convert_to_mattermost_message(
        self,
        content: str,
        channel_id: str,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert CoPaw response to Mattermost message format.
        
        Args:
            content: Message content text
            channel_id: Target Mattermost channel ID
            message_id: Optional message ID for replies
            
        Returns:
            Dictionary formatted for Mattermost API
        """
        message = {
            "channel_id": channel_id,
            "message": content,
        }
        
        if message_id:
            message["root_id"] = message_id
        
        return message

    def should_process_message(self, event_data: Dict[str, Any]) -> bool:
        """
        Determine if a message should be processed.
        
        Checks:
        - Message type is supported
        - Not from bot (if configured)
        - Not a threaded reply we already handled
        
        Args:
            event_data: Raw event data
            
        Returns:
            True if message should be processed
        """
        event_type = event_data.get("event", "")
        
        # Only process supported message types
        if event_type not in self.SUPPORTED_MESSAGE_TYPES:
            return False
        
        # Parse the message
        if event_type == "posted":
            message = self.parse_post_event(event_data)
        elif event_type == "ephemeral_message":
            message = self.parse_ephemeral_event(event_data)
        else:
            return False
        
        if not message:
            return False
        
        # Skip messages from self (bot)
        if message.user_id == self.bot_user_id:
            return False
        
        # Skip empty messages
        if not message.content or not message.content.strip():
            return False
        
        return True


class MattermostEventParser:
    """
    Parser for Mattermost WebSocket events.
    
    Provides extensible event parsing with support for custom event types.
    """

    def __init__(self, converter: MattermostMessageConverter):
        self.converter = converter
        self._custom_parsers: Dict[str, callable] = {}

    def register_parser(self, event_type: str, parser: callable) -> None:
        """
        Register a custom parser for specific event type.
        
        Args:
            event_type: Mattermost event type
            parser: Function that parses event data
        """
        self._custom_parsers[event_type] = parser

    def parse(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse event data using appropriate parser.
        
        Args:
            event_data: Raw WebSocket event data
            
        Returns:
            Parsed event or None
        """
        event_type = event_data.get("event", "")
        
        # Try custom parser first
        if event_type in self._custom_parsers:
            try:
                return self._custom_parsers[event_type](event_data)
            except Exception as e:
                logger.error(f"Custom parser error for {event_type}: {e}")
        
        # Use default parsing for known types
        if event_type == "posted":
            message = self.converter.parse_post_event(event_data)
            if message:
                return self.converter.convert_to_native_payload(message)
        
        elif event_type == "ephemeral_message":
            message = self.converter.parse_ephemeral_event(event_data)
            if message:
                return self.converter.convert_to_native_payload(message)
        
        return None
