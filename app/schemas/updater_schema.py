"""Pydantic schemas for GitHub release data."""

from pydantic import BaseModel, Field


class AssetInfo(BaseModel):
    """A single release asset (the application executable)."""

    name: str
    url: str = Field(description="browser_download_url")
    digest: str = Field(
        default="",
        description='SHA-256 digest in "sha256:..." form',
    )


class ReleaseInfo(BaseModel):
    """A GitHub release as returned by the releases API."""

    tag_name: str
    version: str = ""
    prerelease: bool = False
    published_at: str = ""
    body: str = ""
    assets: list[AssetInfo] = Field(default_factory=list)