from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict


class ConfigSchema(BaseModel):
    """Base Config App Schema."""

    LOG_LVL: str = Field(default="DEBUG")
    APIK: str = Field(default="")

    model_config = SettingsConfigDict(extra="allow", case_sensitive=True)
