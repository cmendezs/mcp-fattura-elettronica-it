"""SDI channel configuration and environment settings."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SDIEnvironment(str, Enum):
    """SDI environment selector."""

    TEST = "test"
    PRODUCTION = "production"


class SDIChannel(str, Enum):
    """SDI transmission channel."""

    SDICOOP = "sdicoop"
    SDIFTP = "sdiftp"


class SDISettings(BaseSettings):
    """Configuration for SDI integration.

    All values can be set via environment variables with the ``SDI_`` prefix,
    or loaded from a ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="SDI_",
        env_file=".env",
        extra="ignore",
    )

    environment: SDIEnvironment = Field(
        default=SDIEnvironment.TEST,
        description="SDI environment: 'test' (interoperability) or 'production'.",
    )
    channel: SDIChannel = Field(
        default=SDIChannel.SDICOOP,
        description="Transmission channel: 'sdicoop' or 'sdiftp'.",
    )
    channel_id: str = Field(
        default="",
        description="Channel ID assigned during AdE accreditation.",
    )
    cert_path: str = Field(
        default="",
        description="Path to the PKCS#12 (.p12/.pfx) mTLS certificate.",
    )
    cert_password: Optional[str] = Field(
        default=None,
        description="Passphrase for the PKCS#12 file.",
    )
    endpoint_url: str = Field(
        default="",
        description=(
            "SDICoop endpoint URL override. When empty, the default URL for "
            "the selected environment is used."
        ),
    )
    timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds.",
    )

    @property
    def effective_endpoint(self) -> str:
        if self.endpoint_url:
            return self.endpoint_url
        # [NEED: verify SDICoop test/production endpoint URLs from AdE accreditation portal]
        if self.environment == SDIEnvironment.TEST:
            return "https://testservizi.fatturapa.it/ricevi_fatture"
        return "https://servizi.fatturapa.it/ricevi_fatture"
