"""Connector interfaces for personal data sources."""

from dash.personal.connectors.base import BaseConnector, SyncResult
from dash.personal.connectors.files import FilesConnector
from dash.personal.connectors.gmail import GmailConnector
from dash.personal.connectors.imessage import IMessageConnector
from dash.personal.connectors.slack import SlackConnector

__all__ = [
    "BaseConnector",
    "SyncResult",
    "GmailConnector",
    "SlackConnector",
    "IMessageConnector",
    "FilesConnector",
]
