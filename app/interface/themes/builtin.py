"""Builtin themes: 7 seed themes + 2 Kanagawa (Wave/Lotus) from rebelot/kanagawa.nvim."""

from app.interface.themes.schema import ThemeDefinition

# Kanagawa palette excerpt from lua/kanagawa/colors.lua
_KANAGAWA_WAVE_COLORS = {
    # Mapped from ThemeColors wave.ui + syn
    # bg = sumiInk3 #1F1F28, bg_m3 = sumiInk0 #16161D, bg_m1 = sumiInk2 #1a1a22
    # palette reference: sumiInk0 #16161D, sumiInk1 #181820,
    # sumiInk3 #1F1F28, sumiInk4 #2A2A37, sumiInk5 #363646, sumiInk6 #54546D
    # crystalBlue #7E9CD8, springViolet2 #9CABCA, waveAqua2 #7AA89F,
    # samuraiRed #E82424
    "primary": "#7E9CD8",
    "on_primary": "#16161D",
    "primary_container": "#2D4F67",
    "on_primary_container": "#DCD7BA",
    "secondary": "#9CABCA",
    "on_secondary": "#16161D",
    "secondary_container": "#223249",
    "on_secondary_container": "#DCD7BA",
    "tertiary": "#7AA89F",
    "on_tertiary": "#16161D",
    "tertiary_container": "#2B3328",
    "on_tertiary_container": "#DCD7BA",
    "error": "#E82424",
    "on_error": "#DCD7BA",
    "error_container": "#43242B",
    "on_error_container": "#DCD7BA",
    "surface": "#1F1F28",
    "on_surface": "#DCD7BA",
    "on_surface_variant": "#C8C093",
    "surface_dim": "#16161D",
    "surface_bright": "#2A2A37",
    "surface_container": "#1A1A22",
    "surface_container_high": "#2A2A37",
    "surface_container_highest": "#363646",
    "surface_container_low": "#181820",
    "surface_container_lowest": "#16161D",
    "outline": "#54546D",
    "outline_variant": "#363646",
    "scrim": "#16161D",
    "shadow": "#16161D",
}

_KANAGAWA_LOTUS_COLORS = {
    # lotus: ui bg = lotusWhite3 #f2ecbc, bg_m3 = lotusWhite0 #d5cea3
    # lotusWhite3 #F2ECBC, lotusWhite0 #D5CEA3, lotusWhite1 #DCD5AC
    # lotusInk1 #545464, dragon etc but for light we use lotus palette
    # lotusBlue4 #4d699b, lotusGreen #6f894e, lotusRed3 #e82424
    "primary": "#4D699B",
    "on_primary": "#F2ECBC",
    "primary_container": "#C7D7E0",
    "on_primary_container": "#545464",
    "secondary": "#6F894E",
    "on_secondary": "#F2ECBC",
    "secondary_container": "#B7D0AE",
    "on_secondary_container": "#545464",
    "tertiary": "#B35B79",
    "on_tertiary": "#F2ECBC",
    "tertiary_container": "#D9A594",
    "on_tertiary_container": "#545464",
    "error": "#E82424",
    "on_error": "#F2ECBC",
    "error_container": "#D9A594",
    "on_error_container": "#545464",
    "surface": "#F2ECBC",
    "on_surface": "#545464",
    "on_surface_variant": "#716E61",
    "surface_dim": "#D5CEA3",
    "surface_bright": "#F2ECBC",
    "surface_container": "#E5DDB0",
    "surface_container_high": "#DCD5AC",
    "surface_container_highest": "#D5CEA3",
    "surface_container_low": "#F2ECBC",
    "surface_container_lowest": "#FFFFFF",
    "outline": "#8A8980",
    "outline_variant": "#DCD7BA",
    "scrim": "#545464",
    "shadow": "#545464",
}

BUILTIN_THEMES: dict[str, ThemeDefinition] = {
    "dark_default": ThemeDefinition(
        id="dark_default",
        name="Dark",
        mode="dark",
        seed="#6750A4",
        is_builtin=True,
    ),
    "light_default": ThemeDefinition(
        id="light_default",
        name="Light",
        mode="light",
        seed="#6750A4",
        is_builtin=True,
    ),
    "midnight": ThemeDefinition(
        id="midnight",
        name="Midnight",
        mode="dark",
        seed="#1A1A2E",
        is_builtin=True,
    ),
    "forest": ThemeDefinition(
        id="forest",
        name="Forest",
        mode="dark",
        seed="#2D5016",
        is_builtin=True,
    ),
    "ocean": ThemeDefinition(
        id="ocean",
        name="Ocean",
        mode="dark",
        seed="#0066CC",
        is_builtin=True,
    ),
    "sunset": ThemeDefinition(
        id="sunset",
        name="Sunset",
        mode="light",
        seed="#FF6B35",
        is_builtin=True,
    ),
    "arctic": ThemeDefinition(
        id="arctic",
        name="Arctic",
        mode="light",
        seed="#E0F2F7",
        is_builtin=True,
    ),
    "kanagawa_wave": ThemeDefinition(
        id="kanagawa_wave",
        name="Kanagawa Wave",
        mode="dark",
        seed="#7E9CD8",
        colors=_KANAGAWA_WAVE_COLORS,
        is_builtin=True,
    ),
    "kanagawa_lotus": ThemeDefinition(
        id="kanagawa_lotus",
        name="Kanagawa Lotus",
        mode="light",
        seed="#4D699B",
        colors=_KANAGAWA_LOTUS_COLORS,
        is_builtin=True,
    ),
}
