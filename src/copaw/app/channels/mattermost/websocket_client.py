# -*- coding: utf-8 -*-
"""
Mattermost WebSocket Client Module

This module provides WebSocket connection management for Mattermost integration,
using the mattermostdriver library which already implements the WebSocket protocol.
"""

import asyncio
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """WebSocket connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class MattermostConfig:
    """Mattermost WebSocket configuration."""
    url: str
    bot_token: str
    team_id: str = ""
    http_proxy: str = ""


class MattermostWebSocketClient:
    """
    Mattermost WebSocket Client using mattermostdriver.
    
    This client wraps mattermostdriver's websocket functionality.
    """

    def __init__(
        self,
        config: MattermostConfig,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        login_callback: Optional[Callable[..., None]] = None,
    ):
        """
        Args:
            config: Mattermost connection configuration.
            loop: The asyncio event loop used by the application. This is
                required to safely schedule async handlers from the
                websocket thread.
            login_callback: Optional callback invoked after successful
                login with the bot user_id. Useful for letting the
                channel know its own bot id.
        """
        self.config = config
        self._driver = None
        self._state = WebSocketState.DISCONNECTED
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = loop
        self._stop_event = threading.Event()
        self._login_callback = login_callback

    @property
    def state(self) -> WebSocketState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == WebSocketState.CONNECTED

    def on(self, event_type: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register event handler for specific event type.

        Handlers can be regular functions or async callables. Async
        handlers will be scheduled onto the configured asyncio event
        loop when events arrive from the websocket thread.
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.debug(f"Registered handler for event: {event_type}")

    def off(self, event_type: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Unregister event handler."""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
            except ValueError:
                pass

    def _create_driver(self):
        """Create Mattermost driver instance."""
        from urllib.parse import urlparse
        from mattermostdriver import Driver
        
        parsed = urlparse(self.config.url)
        scheme = parsed.scheme or 'https'
        host = parsed.netloc.split(':')[0] if parsed.netloc else 'localhost'
        
        # Auto-detect port
        if ':' in parsed.netloc:
            port = int(parsed.netloc.split(':')[1])
        elif scheme == 'https':
            port = 443
        else:
            port = 8065
        
        options = {
            'url': host,
            'token': self.config.bot_token,
            'scheme': scheme,
            'port': port,
            'basepath': '/api/v4',
            'verify': True,
            'timeout': 30,
        }
        
        return Driver(options)

    def _handle_event(self, event_data: Any) -> None:
        """Handle incoming WebSocket event.

        This method is invoked from the mattermostdriver websocket
        thread. It dispatches to registered handlers, scheduling
        async handlers on the main asyncio loop when necessary.
        """
        # mattermostdriver may call event handlers with either a parsed dict
        # or a raw JSON string (depending on version / code path). Normalize.
        if isinstance(event_data, (bytes, bytearray)):
            try:
                event_data = event_data.decode("utf-8", errors="replace")
            except Exception:
                event_data = str(event_data)

        if isinstance(event_data, str):
            try:
                import json

                event_data = json.loads(event_data)
            except Exception:
                # If it's not JSON, we can't parse it into an event dict.
                logger.debug("Mattermost websocket received non-JSON string event")
                return

        if not isinstance(event_data, dict):
            logger.debug(
                "Mattermost websocket received unsupported event type: %s",
                type(event_data),
            )
            return

        event_type = event_data.get('event', '')
        
        if not event_type:
            return
        
        handlers = self._event_handlers.get(event_type, [])
        handlers = handlers + self._event_handlers.get('all', [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    if not self._loop:
                        logger.error(
                            "Async handler registered but no event loop "
                            "configured in MattermostWebSocketClient",
                        )
                        continue
                    asyncio.run_coroutine_threadsafe(
                        handler(event_data),
                        self._loop,
                    )
                else:
                    handler(event_data)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

    def _run_loop(self) -> None:
        """Run the WebSocket client in a thread."""
        # mattermostdriver's init_websocket() uses asyncio.get_event_loop()
        # internally. In Python 3.10+ a non-main thread has no default loop,
        # so we must create and set one for this thread.
        thread_loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(thread_loop)

            # Login
            self._driver.login()
            
            # Get user info via API
            me = self._driver.client.get('/users/me')
            user_id = me.get('id')
            username = me.get('username') or me.get('name') or ""
            
            logger.info(f"Mattermost logged in as user: {user_id}")
            # Notify owner (channel) about bot user id so it can
            # avoid processing its own messages.
            if self._login_callback and user_id:
                try:
                    # Backward-compatible: some callbacks accept only (user_id).
                    try:
                        self._login_callback(user_id, username)
                    except TypeError:
                        self._login_callback(user_id)
                except Exception as e:
                    logger.error(f"Error in login callback: {e}")
            
            # Initialize websocket (mattermostdriver requires a base event handler).
            # Newer mattermostdriver versions await the event handler, so we must
            # pass an async callable here. It forwards events into our dispatch
            # logic (which is thread-safe and schedules async channel handlers
            # onto the app's main loop when needed).
            async def _driver_event_handler(evt: Any) -> None:
                self._handle_event(evt)

            self._driver.init_websocket(_driver_event_handler)
            
            # Set up websocket event callbacks
            self._driver.websocket.add_event_handler('posted', self._handle_event)
            # ephemeral_message: system / ephemeral replies
            self._driver.websocket.add_event_handler('ephemeral_message', self._handle_event)
            # hello: initial handshake / status
            self._driver.websocket.add_event_handler('hello', self._handle_event)
            
            # Connect to websocket
            self._driver.websocket.connect()
            
            self._state = WebSocketState.CONNECTED
            logger.info("Mattermost WebSocket connected successfully")
            
            # Keep running
            self._driver.websocket.run_forever()
            
        except Exception as e:
            logger.error(f"Mattermost WebSocket error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._state = WebSocketState.FAILED
        finally:
            try:
                if thread_loop is not None:
                    thread_loop.close()
            except Exception:
                pass

    async def connect(self) -> bool:
        """Connect to Mattermost WebSocket server."""
        if self.is_connected:
            return True
        
        self._state = WebSocketState.CONNECTING
        
        try:
            # Ensure we have an event loop reference for async handlers
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop in this context; async handlers
                    # will not be supported.
                    logger.warning(
                        "MattermostWebSocketClient.connect called without "
                        "a running event loop; async handlers may not work.",
                    )

            self._driver = self._create_driver()
            
            # Start websocket in a separate thread
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            
            # Wait a bit for connection
            await asyncio.sleep(3)
            
            if self.is_connected:
                return True
            
            # Check if thread is still running
            if self._thread and self._thread.is_alive():
                logger.info("WebSocket thread started, waiting for connection...")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to connect to Mattermost: {e}")
            self._state = WebSocketState.FAILED
            return False

    async def run_forever(self) -> None:
        """Run the WebSocket client indefinitely."""
        await self.connect()
        
        # Keep running
        while self._running:
            await asyncio.sleep(1)
            
            # Check if thread is still alive
            if self._thread and not self._thread.is_alive():
                logger.warning("WebSocket thread died, attempting reconnect...")
                await self.connect()

    async def stop(self) -> None:
        """Stop the WebSocket client."""
        self._running = False
        self._stop_event.set()
        
        try:
            if self._driver and hasattr(self._driver, 'websocket'):
                self._driver.websocket.close()
        except Exception as e:
            logger.debug(f"Error closing websocket: {e}")
        
        self._state = WebSocketState.DISCONNECTED
        logger.info("Mattermost WebSocket client stopped")

    async def send(self, event: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """Send a message through WebSocket."""
        if not self.is_connected or not self._driver:
            logger.warning("Cannot send: not connected")
            return False
        
        try:
            # Use mattermostdriver's websocket to send
            if hasattr(self._driver, 'websocket'):
                self._driver.websocket.send({'action': event, 'data': data or {}})
                return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")
        
        return False
