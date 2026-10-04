# Themes

🌐 Language / Язык **README**: [Русский](README.md) · **English**

Folder for custom themes. The app scans `themes/*.json` automatically on startup and when opening settings.

> **Samples are inactive:** `example_*.json.example` — rename to `example_*.json` (or copy as `my_theme.json`) to activate. See the format below.

## File format

```json
{
  "id": "my_ocean",          // 3-32 chars, a-z, 0-9, _
  "name": "My Ocean",        // 2-40 chars, shown in settings
  "mode": "dark",            // dark | light — affects theme_mode
  "seed": "#0066CC",         // hex #RGB/#RRGGBB, base Material 3 color
  "colors": {                // optional, IDE-style fine tuning
    "primary": "#0066CC",
    "surface": "#101418",
    "surface_container": "#1A1F24"
  }
}
```

### Minimal example (4 fields are enough)

```json
{
  "id": "sunset_custom",
  "name": "Sunset Custom",
  "mode": "light",
  "seed": "#FF6B35"
}
```

### Hybrid: seed + colors

- `seed` — required, generates the whole Material 3 palette.
- `colors` — optional, overrides any tokens. Keys must come from `ColorScheme` (snake_case):

`primary, on_primary, primary_container, secondary, tertiary, surface, on_surface, surface_variant, surface_dim, surface_bright, surface_container, surface_container_high, surface_container_highest, surface_container_low, outline, outline_variant, error, scrim, shadow, surface_tint` (full list in `app/interface/themes/schema.py`).

If `colors` is given without `primary` — `primary` is taken from `seed`.

### Where to get colors for Kanagawa etc.

Original palette: https://github.com/rebelot/kanagawa.nvim (`lua/kanagawa/colors.lua` and `themes.lua`). Built-in `kanagawa_wave` / `kanagawa_lotus` themes use the same hex values.

### Import

1. **By file:** drop `my_theme.json` into this folder, reopen Settings — the theme shows up in the Dropdown.
2. **Via UI:** Settings → `Import` → pick a JSON → the file is copied to `themes/<id>.json` automatically.

### Errors

- Broken JSON or invalid hex → the theme is skipped, `WARNING` in the logs.
- Duplicate `id` → the last file wins (visible in the logs).
- Missing `THEME` in `config.json` → fallback to `dark_default`.
