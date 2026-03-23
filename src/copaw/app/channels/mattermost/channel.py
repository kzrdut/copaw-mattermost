# -*- coding: utf-8 -*-
"""
Mattermost Channel Implementation

Mattermost integration for CoPaw using WebSocket for real-time messaging.

Features:
- WebSocket-based real-time communication
- Support for channel messages, direct messages, and group messages
- Message parsing and conversion
- Automatic reconnection
- Bot command handling

Reference:
- Mattermost WebSocket API: https://developers.mattermost.com/integrate/reference/web-socket-events/
- Mattermost REST API: https://developers.mattermost.com/integrate/reference/web-api/
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
)

import aiohttp

from agentscope_runtime.engine.schemas.agent_schemas import (
    TextContent,
    ImageContent,
    VideoContent,
    AudioContent,
    FileContent,
    ContentType,
)

from ..base import BaseChannel, OnReplySent, ProcessHandler
from ..utils import file_url_to_local_path

from ....config.config import MattermostConfig as MattermostChannelConfig

from .websocket_client import (
    MattermostWebSocketClient,
    MattermostConfig as MMWebSocketConfig,
    WebSocketState,
)
from .message_converter import (
    MattermostMessageConverter,
    MattermostEventParser,
    MattermostMessage,
)

if TYPE_CHECKING:
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

logger = logging.getLogger(__name__)


class MattermostChannel(BaseChannel):
    """
    Mattermost Channel: Real-time messaging via WebSocket.
    
    Handles:
    - WebSocket connection to Mattermost server
    - Incoming message processing
    - Outgoing message sending via REST API
    - Session management
    
    Usage:
        channel = MattermostChannel(
            process=process_handler,
            enabled=True,
            mattermost_url="https://mattermost.example.com",
            bot_token="your-bot-token",
            team_id="your-team-id",
        )
        await channel.start()
    """

    channel = "mattermost"
    uses_manager_queue = True

    def __init__(
        self,
        process: ProcessHandler,
        enabled: bool,
        mattermost_url: str,
        bot_token: str,
        team_id: str,
        http_proxy: str = "",
        bot_prefix: str = "",
        require_mention_in_channels: bool = True,
        allow_dm_without_mention: bool = True,
        command_prefixes: Optional[List[str]] = None,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ):
        super().__init__(
            process,
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
        )
        self.enabled = enabled
        self.mattermost_url = mattermost_url
        self.bot_token = bot_token
        self.team_id = team_id
        self.http_proxy = http_proxy
        self.bot_prefix = bot_prefix
        self.require_mention_in_channels = require_mention_in_channels
        self.allow_dm_without_mention = allow_dm_without_mention
        self.command_prefixes = [p for p in (command_prefixes or []) if (p or "").strip()]

        self._ws_client: Optional[MattermostWebSocketClient] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

        self._message_converter = MattermostMessageConverter()
        self._event_parser = MattermostEventParser(self._message_converter)

        self._channel_cache: Dict[str, Dict[str, Any]] = {}
        self._user_cache: Dict[str, Dict[str, Any]] = {}

        self._session_webhook_store: Dict[str, str] = {}

        self._debounce_seconds = 0.3

        self._bot_user_id: Optional[str] = None
        self._bot_username: str = ""

        logger.info(
            f"Mattermost channel initialized: url={mattermost_url}, "
            f"team_id={team_id}, enabled={enabled}",
        )

    @classmethod
    def from_env(
        cls,
        process: ProcessHandler,
        on_reply_sent: OnReplySent = None,
    ) -> "MattermostChannel":
        """Create channel from environment variables."""
        raw_prefixes = os.getenv("MATTERMOST_COMMAND_PREFIXES", "")
        command_prefixes = [p.strip() for p in raw_prefixes.split(",") if p.strip()]
        return cls(
            process=process,
            enabled=os.getenv("MATTERMOST_CHANNEL_ENABLED", "1") == "1",
            mattermost_url=os.getenv("MATTERMOST_URL", ""),
            bot_token=os.getenv("MATTERMOST_BOT_TOKEN", ""),
            team_id=os.getenv("MATTERMOST_TEAM_ID", ""),
            http_proxy=os.getenv("MATTERMOST_HTTP_PROXY", ""),
            bot_prefix=os.getenv("MATTERMOST_BOT_PREFIX", ""),
            require_mention_in_channels=os.getenv(
                "MATTERMOST_REQUIRE_MENTION_IN_CHANNELS",
                "1",
            )
            == "1",
            allow_dm_without_mention=os.getenv(
                "MATTERMOST_ALLOW_DM_WITHOUT_MENTION",
                "1",
            )
            == "1",
            command_prefixes=command_prefixes,
            on_reply_sent=on_reply_sent,
        )

    @classmethod
    def from_config(
        cls,
        process: ProcessHandler,
        config: MattermostChannelConfig,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ) -> "MattermostChannel":
        """Create channel from config object."""
        return cls(
            process=process,
            enabled=config.enabled,
            mattermost_url=config.mattermost_url,
            bot_token=config.bot_token,
            team_id=config.team_id,
            http_proxy=config.http_proxy or "",
            bot_prefix=config.bot_prefix or "",
            require_mention_in_channels=getattr(
                config,
                "require_mention_in_channels",
                True,
            ),
            allow_dm_without_mention=getattr(config, "allow_dm_without_mention", True),
            command_prefixes=list(getattr(config, "command_prefixes", []) or []),
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
        )

    async def _init_http_session(self) -> None:
        """Initialize HTTP session for REST API calls."""
        if not self._http_session:
            self._http_session = aiohttp.ClientSession()

    async def _get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information from Mattermost."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        await self._init_http_session()

        try:
            async with self._http_session.get(
                f"{self.mattermost_url}/api/v4/users/{user_id}",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    user_info = await resp.json()
                    self._user_cache[user_id] = user_info
                    return user_info
        except Exception as e:
            logger.error(f"Error getting user info: {e}")

        return None

    async def _get_channel_info(
        self,
        channel_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get channel information from Mattermost."""
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]

        await self._init_http_session()

        try:
            async with self._http_session.get(
                f"{self.mattermost_url}/api/v4/channels/{channel_id}",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    channel_info = await resp.json()
                    self._channel_cache[channel_id] = channel_info
                    return channel_info
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")

        return None

    async def _handle_ws_event(self, event_data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket event."""
        event_type = event_data.get("event", "")

        if event_type not in {"posted", "ephemeral_message"}:
            return

        if not self._message_converter.should_process_message(event_data):
            return

        if event_type == "posted":
            message = self._message_converter.parse_post_event(event_data)
        elif event_type == "ephemeral_message":
            message = self._message_converter.parse_ephemeral_event(event_data)
        else:
            return

        if not message:
            return

        # Gate: in public/private channels, only process messages that mention
        # the bot (or match a command prefix). DMs/group DMs can be exempted.
        channel_info = await self._get_channel_info(message.channel_id)
        channel_type = (channel_info or {}).get("type")  # O/P/D/G
        is_dm = channel_type in ("D", "G")

        if self.require_mention_in_channels and not (is_dm and self.allow_dm_without_mention):
            text = (message.content or "").strip()
            mentioned = False
            if self._bot_user_id:
                mentioned = f"<@{self._bot_user_id}>" in text
            if not mentioned and self._bot_username:
                # Mattermost commonly stores mentions as "@username" in message text.
                try:
                    mentioned = bool(
                        re.search(
                            rf"(^|\s)@{re.escape(self._bot_username)}(\b|\s|$)",
                            text,
                        ),
                    )
                except Exception:
                    mentioned = f"@{self._bot_username}" in text
            has_cmd_prefix = any(text.startswith(p) for p in self.command_prefixes)
            has_bot_prefix = bool(self.bot_prefix and text.startswith(self.bot_prefix))
            if not (mentioned or has_cmd_prefix or has_bot_prefix):
                logger.info(
                    "Mattermost drop (require mention): channel_id=%s type=%s user=%s text_preview=%s",
                    message.channel_id,
                    channel_type,
                    message.username,
                    text[:80].replace("\n", " "),
                )
                return

        logger.debug(
            f"Received message: channel={message.channel_id}, "
            f"user={message.username}, content={message.content[:50]}",
        )

        native_payload = self._message_converter.convert_to_native_payload(message)

        # Store channel info for replies / session resolution
        if channel_info:
            native_payload["meta"]["channel_name"] = channel_info.get("name")
            native_payload["meta"]["channel_type"] = channel_type
            native_payload["meta"]["username"] = message.username

        if self._enqueue:
            self._enqueue(native_payload)
        else:
            logger.warning("Mattermost: _enqueue not set, message dropped")

    async def _run_ws_client(self) -> None:
        """Run WebSocket client in background."""
        if not self.enabled:
            return

        ws_config = MMWebSocketConfig(
            url=self.mattermost_url,
            bot_token=self.bot_token,
            team_id=self.team_id,
            http_proxy=self.http_proxy,
        )

        loop = asyncio.get_running_loop()

        def _on_login(bot_user_id: str, bot_username: str = "") -> None:
            """
            Callback invoked by the websocket client after successful login.

            We use this to record the bot's own user id so that incoming
            messages from the bot can be filtered out by the converter.
            """
            self._bot_user_id = bot_user_id
            self._bot_username = (bot_username or "").strip()
            self._message_converter.bot_user_id = bot_user_id
            logger.info(
                "Mattermost bot identity set: user_id=%s username=%s",
                bot_user_id,
                self._bot_username,
            )

        self._ws_client = MattermostWebSocketClient(
            ws_config,
            loop=loop,
            login_callback=_on_login,
        )

        self._ws_client.on("posted", self._handle_ws_event)
        self._ws_client.on("ephemeral_message", self._handle_ws_event)

        logger.info("Starting Mattermost WebSocket client...")
        await self._ws_client.run_forever()

    async def start(self) -> None:
        """Start the Mattermost channel."""
        if not self.enabled:
            logger.info("Mattermost channel is disabled")
            return

        if not self.mattermost_url or not self.bot_token:
            logger.error("Mattermost: missing URL or bot token")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_ws_client(), name="mattermost_ws")

        logger.info("Mattermost channel started")

    async def stop(self) -> None:
        """Stop the Mattermost channel."""
        self._running = False

        if self._ws_client:
            await self._ws_client.stop()

        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        logger.info("Mattermost channel stopped")

    def resolve_session_id(
        self,
        sender_id: str,
        channel_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Resolve session ID from sender and channel info.
        
        Session format: mattermost:ch:<channel_id> or mattermost:dm:<user_id>
        """
        meta = channel_meta or {}
        channel_id = meta.get("channel_id", "")
        channel_type = meta.get("channel_type", "O")
        user_id = meta.get("user_id", sender_id)

        # Direct message (D) or Group message (G)
        if channel_type in ("D", "G"):
            return f"mattermost:dm:{user_id}"

        # Channel message
        if channel_id:
            return f"mattermost:ch:{channel_id}"

        return f"mattermost:dm:{user_id}"

    def build_agent_request_from_native(
        self,
        native_payload: Any,
    ) -> "AgentRequest":
        """Build AgentRequest from Mattermost message payload."""
        payload = native_payload if isinstance(native_payload, dict) else {}

        channel_id = payload.get("channel_id") or self.channel
        sender_id = payload.get("sender_id") or ""
        content_parts = payload.get("content_parts", [])
        meta = payload.get("meta", {})
        user_id = meta.get("user_id", sender_id)

        # Convert content parts to runtime format
        runtime_parts = []
        for part in content_parts:
            if isinstance(part, dict):
                part_type = part.get("type", "text")
                if part_type == "text":
                    text = part.get("text", "")
                    if text:
                        runtime_parts.append(
                            TextContent(type=ContentType.TEXT, text=text),
                        )
                elif part_type == "image":
                    runtime_parts.append(
                        ImageContent(
                            type=ContentType.IMAGE,
                            image_url=part.get("url", ""),
                        ),
                    )
            elif isinstance(part, str) and part:
                runtime_parts.append(
                    TextContent(type=ContentType.TEXT, text=part),
                )

        if not runtime_parts:
            runtime_parts = [
                TextContent(type=ContentType.TEXT, text=""),
            ]

        session_id = self.resolve_session_id(user_id, meta)

        request = self.build_agent_request_from_user_content(
            channel_id=channel_id,
            sender_id=sender_id,
            session_id=session_id,
            content_parts=runtime_parts,
            channel_meta=meta,
        )

        request.user_id = user_id
        request.channel_meta = meta

        return request

    def get_to_handle_from_request(self, request: "AgentRequest") -> str:
        """Get send target from request."""
        meta = getattr(request, "channel_meta", None) or {}
        channel_id = meta.get("channel_id", "")
        user_id = meta.get("user_id", "")

        if channel_id:
            return channel_id

        return user_id

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Send message via Mattermost REST API.
        
        Args:
            to_handle: Channel ID or user ID
            text: Message text
            meta: Additional metadata (channel_id, user_id, etc.)
        """
        if not self.enabled:
            return

        await self._init_http_session()

        meta = meta or {}
        channel_id = meta.get("channel_id", to_handle)

        if not channel_id:
            logger.warning("Mattermost: no channel_id for send")
            return

        # Prepend greeting with username to the output message
        user_id = (meta.get("user_id") or "").strip()
        username = (meta.get("username") or "").strip()
        if username:
            text = f"@{username} 你好！\n{text}"
        elif user_id:
            text = f"@{user_id} 你好！\n{text}"

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

        message_data = {
            "channel_id": channel_id,
            "message": text,
        }

        # Handle root_id for thread replies
        root_id = meta.get("message_id")
        if root_id:
            message_data["root_id"] = root_id

        try:
            async with self._http_session.post(
                f"{self.mattermost_url}/api/v4/posts",
                headers=headers,
                json=message_data,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 201:
                    logger.debug(f"Message sent to channel {channel_id}")
                else:
                    error_text = await resp.text()
                    logger.error(
                        f"Failed to send message: {resp.status} - {error_text}",
                    )
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def send_media(
        self,
        to_handle: str,
        part: Any,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send media attachment."""
        if not self.enabled:
            return

        meta = meta or {}
        channel_id = meta.get("channel_id", to_handle)

        if not channel_id:
            return

        part_type = getattr(part, "type", None)

        if part_type == ContentType.IMAGE:
            image_url = getattr(part, "image_url", None)
            if image_url:
                await self.send(to_handle, f"![Image]({image_url})", meta)

        elif part_type == ContentType.VIDEO:
            video_url = getattr(part, "video_url", None)
            if video_url:
                await self.send(to_handle, f"[Video]({video_url})", meta)

        elif part_type == ContentType.FILE:
            file_url = getattr(part, "file_url", None)
            if file_url:
                await self.send(to_handle, f"[File]({file_url})", meta)

    def to_handle_from_target(self, *, user_id: str, session_id: str) -> str:
        """Map cron dispatch target to channel-specific to_handle."""
        if session_id:
            parts = session_id.split(":")
            if len(parts) >= 3:
                if parts[1] == "ch":
                    return parts[2]
                elif parts[1] == "dm":
                    return parts[2]
        return user_id
