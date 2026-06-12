"""
Message Gateway module — multi-channel messaging (CLI, Slack, Telegram).

Exporta las clases principales:
- MessageGateway (abstract base)
- CliGateway, SlackGateway, TelegramGateway
- create_gateway (factory)
- GatewayManager
"""

from harness.gateway.gateway import (
    CliGateway,
    GatewayManager,
    Message,
    MessageGateway,
    SlackGateway,
    TelegramGateway,
    create_gateway,
    load_gateway_config,
)

__all__ = [
    "CliGateway",
    "GatewayManager",
    "Message",
    "MessageGateway",
    "SlackGateway",
    "TelegramGateway",
    "create_gateway",
    "load_gateway_config",
]
