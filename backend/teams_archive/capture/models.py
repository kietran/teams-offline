from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ChannelIdentity:
    id: str
    team_id: str
    team_name: str
    display_name: str
    source_locator: str
    identity_confidence: str
    membership_type: str = "unknown"
    web_url: str | None = None

    def api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "teamId": self.team_id,
            "teamName": self.team_name,
            "displayName": self.display_name,
            "sourceLocator": self.source_locator,
            "identityConfidence": self.identity_confidence,
            "membershipType": self.membership_type,
            "webUrl": self.web_url,
        }


@dataclass(frozen=True)
class ChromeState:
    installed: bool
    running: bool
    signed_in: bool
    needs_login: bool
    current_channel: dict[str, Any] | None = None

    def api_dict(self) -> dict[str, Any]:
        return asdict(self)
