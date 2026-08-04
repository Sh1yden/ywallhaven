"""Application configuration schema."""

from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict


class ConfigSchema(BaseModel):
    """Base application config schema with defaults for dev mode."""

    MODE: str = Field(default="dev", description="App mode for logs, dev or prod")
    LOG_LVL: str = Field(default="DEBUG")
    PORT: int = Field(default=9864)
    APIK: str = Field(default="")

    model_config = SettingsConfigDict(extra="allow", case_sensitive=True)
