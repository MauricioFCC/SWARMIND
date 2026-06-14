"""
Message Gateway — Abstract multi-channel messaging layer.

Supports CLI (stdin/stdout), Slack (optional), and Telegram (optional)
gateways. If a gateway is missing its token, it gracefully deactivates
with a warning.
"""

from __future__ import annotations

import abc
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config path
# ---------------------------------------------------------------------------

GATEWAY_CONFIG_PATH = Path(__file__).resolve().parent / "gateway_config.yaml"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A message exchanged through a gateway."""

    role: str  # "user", "agent", "system"
    content: str
    channel: str  # e.g. "cli", "#general", "#dev"
    timestamp: str = ""

    def __post_init__(self) -> None:
        """Post init."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, str]:
        """To dict."""
        return {
            "role": self.role,
            "content": self.content,
            "channel": self.channel,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class MessageGateway(abc.ABC):
    """Abstract message gateway. Subclasses must implement send and receive."""

    @abc.abstractmethod
    def send(self, message: Message) -> bool:
        """Send a message through this gateway. Returns True on success."""
        ...

    @abc.abstractmethod
    def receive(self) -> List[Message]:
        """Receive pending messages from this gateway."""
        ...

    @abc.abstractmethod
    def is_active(self) -> bool:
        """Return True if this gateway is fully configured and operational."""
        ...


# ---------------------------------------------------------------------------
# CLI Gateway
# ---------------------------------------------------------------------------


class CliGateway(MessageGateway):
    """
    CLI message gateway — reads from stdin, writes to stdout.

    This gateway is always active (no token required).
    """

    def __init__(self) -> None:
        """Inicializa la instancia de la clase."""
        self._buffer: List[Message] = []

    def send(self, message: Message) -> bool:
        """Write a message to stdout."""
        try:
            prefix = f"[{message.channel}] {message.role}:"
            logger.info(f"{prefix} {message.content}", file=sys.stdout, flush=True)
            return True
        except OSError as exc:
            logger.error("CLI send failed: %s", exc)
            return False

    def receive(self) -> List[Message]:
        """Read a single line from stdin (if available) and return as message."""
        try:
            if sys.stdin.isatty():
                return []  # interactive — no auto-read
            line = sys.stdin.readline()
            if line:
                msg = Message(
                    role="user",
                    content=line.strip(),
                    channel="cli",
                )
                self._buffer.append(msg)
                return [msg]
        except Exception as exc:
            logger.debug("CLI receive error (non-fatal): %s", exc)
        return []

    def is_active(self) -> bool:
        """Is active."""
        return True


# ---------------------------------------------------------------------------
# Slack Gateway (optional)
# ---------------------------------------------------------------------------


class SlackGateway(MessageGateway):
    """
    Slack message gateway. Requires a Slack Bot Token.

    If the token is empty, the gateway deactivates with a warning.
    """

    def __init__(self, token: str = "", channel: str = "#dev") -> None:
        """Inicializa la instancia de la clase."""
        self._token = token
        self._channel = channel
        self._client: Any = None
        self._active = bool(token)

        if self._active:
            self._try_connect()
        else:
            logger.warning(
                "Slack gateway: no token provided. Gateway is DISABLED. "
                "Set slack.token in gateway_config.yaml to enable."
            )

    def _try_connect(self) -> None:
        """Attempt to initialise the Slack SDK client."""
        try:
            from slack_sdk import WebClient  # type: ignore[import-untyped]
            self._client = WebClient(token=self._token)
            # Test connection
            response = self._client.auth_test()
            if response.get("ok"):
                logger.info("Slack gateway connected as %s", response.get("user_id"))
            else:
                logger.warning("Slack auth_test failed: %s", response)
                self._active = False
        except ImportError:
            logger.warning(
                "slack_sdk not installed. Install with: pip install slack_sdk"
            )
            self._active = False
        except Exception as exc:
            logger.warning("Slack connection failed: %s", exc)
            self._active = False

    def send(self, message: Message) -> bool:
        """Send."""
        if not self._active or self._client is None:
            return False
        try:
            target = message.channel if message.channel != "cli" else self._channel
            self._client.chat_postMessage(
                channel=target,
                text=f"[{message.role}] {message.content}",
            )
            return True
        except Exception as exc:
            logger.error("Slack send failed: %s", exc)
            return False

    def receive(self) -> List[Message]:
        """Receive."""
        if not self._active or self._client is None:
            return []
        try:
            result = self._client.conversations_history(channel=self._channel, limit=5)
            messages: List[Message] = []
            for msg in result.get("messages", []):
                text = msg.get("text", "")
                user = msg.get("user", "unknown")
                if text:
                    messages.append(
                        Message(
                            role="user",
                            content=text,
                            channel=self._channel,
                        )
                    )
            return messages
        except Exception as exc:
            logger.debug("Slack receive error: %s", exc)
            return []

    def is_active(self) -> bool:
        """Is active."""
        return self._active


# ---------------------------------------------------------------------------
# Telegram Gateway (optional)
# ---------------------------------------------------------------------------


class TelegramGateway(MessageGateway):
    """
    Telegram message gateway. Requires a Bot Token and Chat ID.

    If the token is empty, the gateway deactivates with a warning.
    """

    def __init__(self, token: str = "", chat_id: str = "") -> None:
        """Inicializa la instancia de la clase."""
        self._token = token
        self._chat_id = chat_id
        self._active = bool(token) and bool(chat_id)

        if not self._active:
            missing = []
            if not token:
                missing.append("token")
            if not chat_id:
                missing.append("chat_id")
            logger.warning(
                "Telegram gateway: missing %s. Gateway is DISABLED. "
                "Set telegram.token and telegram.chat_id in gateway_config.yaml to enable.",
                ", ".join(missing),
            )

    def send(self, message: Message) -> bool:
        """Send."""
        if not self._active:
            return False
        try:
            import requests  # type: ignore[import-untyped]

            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": f"[{message.role}] {message.content}",
                "parse_mode": "Markdown",
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            logger.warning("Telegram send failed: %s", response.text)
            return False
        except ImportError:
            logger.warning("requests library not installed. Install with: pip install requests")
            return False
        except Exception as exc:
            logger.error("Telegram send error: %s", exc)
            return False

    def receive(self) -> List[Message]:
        """Receive."""
        if not self._active:
            return []
        try:
            import requests

            url = f"https://api.telegram.org/bot{self._token}/getUpdates"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return []
            data = response.json()
            messages: List[Message] = []
            for update in data.get("result", []):
                msg_data = update.get("message", {})
                text = msg_data.get("text", "")
                if text:
                    messages.append(
                        Message(
                            role="user",
                            content=text,
                            channel="telegram",
                        )
                    )
            return messages
        except Exception as exc:
            logger.debug("Telegram receive error: %s", exc)
            return []

    def is_active(self) -> bool:
        """Is active."""
        return self._active


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_gateway(gateway_type: str, config: Optional[Dict[str, Any]] = None) -> MessageGateway:
    """
    Factory function to create the appropriate gateway.

    Args:
        gateway_type: One of "cli", "slack", "telegram".
        config: Optional dict with keys like ``token``, ``channel``, ``chat_id``.

    Returns:
        A ``MessageGateway`` instance.

    Raises:
        ValueError: If the gateway type is unknown.
    """
    config = config or {}

    if gateway_type == "cli":
        return CliGateway()

    elif gateway_type == "slack":
        return SlackGateway(
            token=config.get("token", ""),
            channel=config.get("channel", "#dev"),
        )

    elif gateway_type == "telegram":
        return TelegramGateway(
            token=config.get("token", ""),
            chat_id=config.get("chat_id", ""),
        )

    else:
        raise ValueError(
            f"Unknown gateway type '{gateway_type}'. "
            f"Valid options: 'cli', 'slack', 'telegram'."
        )


# ---------------------------------------------------------------------------
# Load config from YAML
# ---------------------------------------------------------------------------


def load_gateway_config() -> Dict[str, Any]:
    """Load gateway configuration from gateway_config.yaml."""
    if not GATEWAY_CONFIG_PATH.exists():
        logger.warning("Gateway config not found: %s. Using defaults.", GATEWAY_CONFIG_PATH)
        return {
            "active_gateways": ["cli"],
            "slack": {"enabled": False, "token": "", "channel": "#dev"},
            "telegram": {"enabled": False, "token": "", "chat_id": ""},
        }
    try:
        with open(str(GATEWAY_CONFIG_PATH), "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as exc:
        logger.warning("Failed to load gateway config: %s. Using defaults.", exc)
        return {
            "active_gateways": ["cli"],
            "slack": {"enabled": False, "token": "", "channel": "#dev"},
            "telegram": {"enabled": False, "token": "", "chat_id": ""},
        }


# ---------------------------------------------------------------------------
# Gateway manager
# ---------------------------------------------------------------------------


class GatewayManager:
    """
    Manages multiple gateways and provides a unified send/receive interface.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Inicializa la instancia de la clase."""
        self._config = config or load_gateway_config()
        self._gateways: Dict[str, MessageGateway] = {}
        self._init_gateways()

    def _init_gateways(self) -> None:
        """Initialise all configured gateways."""
        active = self._config.get("active_gateways", ["cli"])

        for gw_type in active:
            gw_config = self._config.get(gw_type, {})
            try:
                gateway = create_gateway(gw_type, gw_config)
                self._gateways[gw_type] = gateway
                if gateway.is_active():
                    logger.info("Gateway '%s' initialized and active.", gw_type)
                else:
                    logger.info("Gateway '%s' initialized but INACTIVE (check config).", gw_type)
            except ValueError as exc:
                logger.warning("Failed to create gateway '%s': %s", gw_type, exc)

    def send_all(self, message: Message) -> Dict[str, bool]:
        """Send a message through all active gateways."""
        results: Dict[str, bool] = {}
        for name, gw in self._gateways.items():
            if gw.is_active():
                results[name] = gw.send(message)
        return results

    def receive_all(self) -> Dict[str, List[Message]]:
        """Receive messages from all active gateways."""
        results: Dict[str, List[Message]] = {}
        for name, gw in self._gateways.items():
            if gw.is_active():
                messages = gw.receive()
                if messages:
                    results[name] = messages
        return results

    def get_gateway(self, name: str) -> Optional[MessageGateway]:
        """Get a specific gateway by name."""
        return self._gateways.get(name)

    def list_active_gateways(self) -> List[str]:
        """Return names of active gateways."""
        return [name for name, gw in self._gateways.items() if gw.is_active()]

    def list_all_gateways(self) -> List[str]:
        """Return names of all configured gateways."""
        return list(self._gateways.keys())
