# Themes

Папка для пользовательских тем. Приложение автоматически сканирует `themes/*.json` при старте и при открытии настроек.

> **Примеры неактивны:** `example_*.json.example` — переименуйте в `example_*.json` (или скопируйте как `my_theme.json`) чтобы активировать. См. формат ниже.

## Формат файла

```json
{
  "id": "my_ocean",          // 3-32 символов, a-z, 0-9, _
  "name": "My Ocean",        // 2-40 символов, отображается в настройках
  "mode": "dark",            // dark | light — влияет на theme_mode
  "seed": "#0066CC",         // hex #RGB/#RRGGBB, базовый цвет Material 3
  "colors": {                // опционально, тонкая настройка как в IDE
    "primary": "#0066CC",
    "surface": "#101418",
    "surface_container": "#1A1F24"
  }
}
```

### Минимальный пример (достаточно 4 полей)

```json
{
  "id": "sunset_custom",
  "name": "Sunset Custom",
  "mode": "light",
  "seed": "#FF6B35"
}
```

### Гибрид: seed + colors

- `seed` — обязателен, генерирует всю Material 3 палитру.
- `colors` — опционален, перетирает любые токены. Ключи должны быть из `ColorScheme` (snake_case):

`primary, on_primary, primary_container, secondary, tertiary, surface, on_surface, surface_variant, surface_dim, surface_bright, surface_container, surface_container_high, surface_container_highest, surface_container_low, outline, outline_variant, error, scrim, shadow, surface_tint` (полный список в `app/interface/themes/schema.py`).

Если `colors` указан без `primary` — `primary` возьмётся из `seed`.

### Где брать цвета для Kanagawa и т.д.

Оригинальная палитра: https://github.com/rebelot/kanagawa.nvim (`lua/kanagawa/colors.lua` и `themes.lua`). Built-in темы `kanagawa_wave` / `kanagawa_lotus` используют те же hex.

### Импорт

1. **Файлом:** кинь `my_theme.json` в эту папку, переоткрой Settings — тема появится в Dropdown.
2. **Через UI:** Settings → `Import` → выбери JSON → файл скопируется в `themes/<id>.json` автоматически.

### Ошибки

- Битый JSON или неверный hex → тема пропускается, в логах `WARNING`.
- Дубликат `id` → последний файл побеждает (видно в логах).
- Несуществующий `THEME` в `config.json` → fallback на `dark_default`.
