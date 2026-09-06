"""Theme definition schema with validation and Flet conversion."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_ALLOWED_COLOR_KEYS = {
    "primary",
    "on_primary",
    "primary_container",
    "on_primary_container",
    "primary_fixed",
    "primary_fixed_dim",
    "on_primary_fixed",
    "on_primary_fixed_variant",
    "secondary",
    "on_secondary",
    "secondary_container",
    "on_secondary_container",
    "secondary_fixed",
    "secondary_fixed_dim",
    "on_secondary_fixed",
    "on_secondary_fixed_variant",
    "tertiary",
    "on_tertiary",
    "tertiary_container",
    "on_tertiary_container",
    "tertiary_fixed",
    "tertiary_fixed_dim",
    "on_tertiary_fixed",
    "on_tertiary_fixed_variant",
    "error",
    "on_error",
    "error_container",
    "on_error_container",
    "surface",
    "on_surface",
    "on_surface_variant",
    "surface_dim",
    "surface_bright",
    "surface_container",
    "surface_container_high",
    "surface_container_highest",
    "surface_container_low",
    "surface_container_lowest",
    "inverse_surface",
    "inverse_primary",
    "on_inverse_surface",
    "outline",
    "outline_variant",
    "scrim",
    "shadow",
    "surface_tint",
}

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ID_RE = re.compile(r"^[a-z0-9_]{3,32}$")


def _normalize_hex(value: str) -> str:
    """Expand 3-digit hex to 6-digit and upper-ish normalize.

    Args:
        value: Hex color string.

    Returns:
        Normalized hex string with leading # and 6 or 8 digits.
    """
    v = value.strip()
    if len(v) == 4:  # #RGB
        v = "#" + "".join(c * 2 for c in v[1:])
    return v.upper() if len(v) == 7 else v


class ThemeDefinition(BaseModel):
    """Single theme definition, builtin or user.

    Attributes:
        id: Slug identifier, e.g. 'kanagawa_wave'.
        name: Human readable name.
        mode: Material brightness.
        seed: Base color for M3 generation, hex.
        colors: Optional explicit ColorScheme overrides.
        is_builtin: Whether shipped with app.
    """

    id: str = Field(description="Slug identifier")
    name: str = Field(min_length=2, max_length=40)
    mode: Literal["dark", "light"]
    seed: str = Field(description="Hex seed color, e.g. #7E9CD8")
    colors: dict[str, str] | None = Field(
        default=None, description="Optional ColorScheme overrides"
    )
    is_builtin: bool = False

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(
                "id must be 3-32 chars, lowercase a-z, 0-9, underscore"
            )
        return v

    @field_validator("seed")
    @classmethod
    def _validate_seed(cls, v: str) -> str:
        if not _HEX_RE.match(v.strip()):
            raise ValueError("seed must be hex #RGB, #RRGGBB or #RRGGBBAA")
        return _normalize_hex(v)

    @field_validator("colors")
    @classmethod
    def _validate_colors(
        cls, v: dict[str, str] | None
    ) -> dict[str, str] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("colors must be a dict")
        if len(v) > 40:
            raise ValueError("colors too many keys (max 40)")
        normalized: dict[str, str] = {}
        for key, hex_val in v.items():
            if key not in _ALLOWED_COLOR_KEYS:
                raise ValueError(
                    f"unknown color key '{key}'. "
                    f"Allowed: {', '.join(sorted(_ALLOWED_COLOR_KEYS))}"
                )
            if not isinstance(hex_val, str) or not _HEX_RE.match(
                hex_val.strip()
            ):
                raise ValueError(
                    f"color '{key}' must be hex #RGB/#RRGGBB"
                )
            normalized[key] = _normalize_hex(hex_val)
        return normalized

    def to_flet_theme(self):  # type: ignore[no-untyped-def]
        """Convert to Flet Theme.

        Returns:
            Flet Theme instance.
        """
        from flet import ColorScheme, Theme

        # Pure seed path -> let Flutter generate Material 3 scheme
        if not self.colors:
            return Theme(
                color_scheme_seed=self.seed,
                use_material3=True,
            )

        # Hybrid: explicit ColorScheme. Ensure primary exists.
        cs_kwargs = dict(self.colors)
        if "primary" not in cs_kwargs:
            cs_kwargs["primary"] = self.seed
        # Flet ColorScheme expects snake_case, but keys are already snake
        # but we allow both camel? normalized to snake below
        # Our allowed keys are snake_case already.
        cs = ColorScheme(**cs_kwargs)
        return Theme(
            color_scheme=cs,
            use_material3=True,
        )
