"""Settings panel: blurred overlay shown above the whole interface."""

from typing import Callable

import json
from pathlib import Path

from flet import (
    Alignment,
    Blur,
    ClipBehavior,
    Colors,
    Column,
    Container,
    CrossAxisAlignment,
    Dropdown,
    DropdownOption,
    FilePicker,
    FilePickerFileType,
    FilledButton,
    FilledTonalButton,
    IconButton,
    Icons,
    MainAxisAlignment,
    Margin,
    Padding,
    Row,
    SnackBar,
    SnackBarBehavior,
    Stack,
    Switch,
    Text,
    TextField,
)

from app.core import config, get_logger
from app.core.error_handling import guard
from app.core.version import __version__
from app.interface.components.update_dialog import check_and_offer

_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]

_lg = get_logger()


class SettingsPanel(Container):
    """Fullscreen settings overlay with a blurred backdrop.

    The panel mirrors every field of the config file: theme, API key,
    mode, log level, port and the update toggles. The values are only
    written to config.json when the Save button is pressed; mode, log
    level and port still need an application restart to take effect.
    """

    def __init__(
        self,
        on_api_key_change: Callable[[str], None] | None = None,
        theme_picker: FilePicker | None = None,
    ) -> None:
        super().__init__()
        self._on_api_key_change = on_api_key_change
        self.expand = True
        self.visible = False
        if theme_picker is None:
            raise ValueError("theme_picker must be provided from flet_app")
        self._theme_picker = theme_picker
        self.content = self._build_overlay()

    # Public API ----------------------------------------------------

    def toggle_settings(self, e) -> None:
        """Open or close the settings overlay.

        Args:
            e: Click event from the gear icon.
        """
        if not self.visible:
            self._sync_from_config()
        self.visible = not self.visible
        _lg.debug(
            f"Settings overlay {'opened' if self.visible else 'closed'}."
        )
        self.update()

    def open_settings(self, e) -> None:
        """Show the settings overlay.

        Args:
            e: Click event.
        """
        self._sync_from_config()
        self.visible = True
        _lg.debug("Settings overlay opened.")
        self.update()

    def close_settings(self, e) -> None:
        """Hide the settings overlay.

        Args:
            e: Click event from the close button or backdrop.
        """
        self.visible = False
        _lg.debug("Settings overlay closed.")
        self.update()

    # Event handlers ------------------------------------------------

    def _on_save(self, e) -> None:
        """Validate, persist and apply the edited settings.

        Args:
            e: Click event from the save button.
        """
        old_data = config.data
        old_api_key = old_data.APIK
        api_key = (self._api_key_field.value or "").strip()

        try:
            port = int((self._port_field.value or "").strip() or 0)
        except ValueError:
            _lg.warning("Settings save aborted: invalid port value.")
            self._port_field.error = "Invalid port"
            self._port_field.update()
            return

        old_theme = old_data.THEME
        new_theme = self._theme_dd.value or old_theme

        updates = {
            "THEME": new_theme,
            "APIK": api_key,
            "MODE": self._mode_dd.value or old_data.MODE,
            "LOG_LVL": self._log_lvl_dd.value or old_data.LOG_LVL,
            "PORT": port,
            "CHECK_UPDATES": bool(self._check_updates_sw.value),
            "CHECK_PRERELEASES": bool(self._prereleases_sw.value),
        }

        changed = [
            key for key, value in updates.items()
            if getattr(old_data, key) != value
        ]
        if "APIK" in changed:
            changed.remove("APIK")
        api_key_changed = api_key != old_api_key

        try:
            config.update(**updates)
        except Exception as exc:
            _lg.error(
                f"Failed to save settings: {exc}.",
                exc_info=True,
            )
            self._show_save_error()
            return

        if changed or api_key_changed:
            details = ", ".join(changed) if changed else "none"
            if api_key_changed:
                details += ", API key updated"
            _lg.info(f"Settings saved. Changed: {details}.")
        else:
            _lg.info("Settings saved; no changes.")

        if new_theme != old_theme:
            _lg.info(f"Applying theme {old_theme} -> {new_theme}.")
            try:
                from app.interface.themes import apply_theme

                apply_theme(self.page, new_theme)
            except Exception as e:
                _lg.warning(f"Failed to apply theme {new_theme}: {e}")
                self.page.update()

        if self._on_api_key_change is not None and api_key_changed:
            _lg.debug("Propagating the new API key to the left panel.")
            self._on_api_key_change(api_key)

        self._show_saved_notice()

    @guard
    def _on_check_updates(self, e) -> None:
        """Run a manual update check in the background.

        Args:
            e: Click event from the update button.
        """
        _lg.info("Manual update check requested.")
        self.close_settings(e)
        self.page.run_task(check_and_offer, self.page, manual=True)

    # Private helpers -----------------------------------------------

    def _sync_from_config(self) -> None:
        """Refresh the panel fields from the current config values."""
        # Reload user themes so dropdown shows fresh imports/files
        try:
            from app.interface.themes import reload_user_themes

            reload_user_themes()
            self._refresh_theme_options()
        except Exception as e:
            _lg.debug(f"Failed to reload themes: {e}")
        data = config.data
        self._theme_dd.value = data.THEME
        self._api_key_field.value = data.APIK
        self._mode_dd.value = data.MODE
        self._log_lvl_dd.value = data.LOG_LVL
        self._port_field.value = str(data.PORT)
        self._check_updates_sw.value = data.CHECK_UPDATES
        self._prereleases_sw.value = data.CHECK_PRERELEASES

    def _refresh_theme_options(self) -> None:
        """Rebuild theme dropdown options from registry."""
        try:
            from app.interface.themes import list_themes

            themes = list_themes()
            # Sort: builtin first alphabetically, then user
            def _sort_key(item):  # type: ignore[no-untyped-def]
                _id, td = item
                return (0 if td.is_builtin else 1, td.name.lower())

            sorted_items = sorted(themes.items(), key=_sort_key)
            self._theme_dd.options = [
                DropdownOption(key=tid, text=td.name)
                for tid, td in sorted_items
            ]
            if hasattr(self, "_theme_dd"):
                try:
                    self._theme_dd.update()
                except Exception:
                    pass
        except Exception as e:
            _lg.debug(f"Failed to refresh theme options: {e}")

    async def _on_import_theme(self, e) -> None:
        """Open file picker for theme JSON."""
        try:
            files = await self._theme_picker.pick_files(
                dialog_title="Import theme JSON",
                allowed_extensions=["json"],
                file_type=FilePickerFileType.CUSTOM,
                allow_multiple=False,
            )
            if files:
                await self._handle_theme_files(files)
        except Exception as ex:
            _lg.warning(f"Import picker failed: {ex}")
            self.page.show_dialog(
                SnackBar(
                    content=Text(f"Import failed: {ex}"),
                    behavior=SnackBarBehavior.FLOATING,
                    bgcolor=Colors.RED,
                )
            )

    async def _handle_theme_files(self, files) -> None:  # type: ignore[no-untyped-def]
        """Handle picked theme files: validate and copy to themes/."""
        if not files:
            return
        picked = files[0]
        src_path = getattr(picked, "path", None)
        if not src_path:
            self.page.show_dialog(
                SnackBar(
                    content=Text("No file selected"),
                    behavior=SnackBarBehavior.FLOATING,
                    bgcolor=Colors.RED,
                )
            )
            return
        src = Path(src_path)
        try:
            raw = json.loads(src.read_text(encoding="utf-8"))
        except Exception as ex:
            _lg.warning(f"Theme import invalid JSON {src}: {ex}")
            self.page.show_dialog(
                SnackBar(
                    content=Text("Invalid JSON"),
                    behavior=SnackBarBehavior.FLOATING,
                    bgcolor=Colors.RED,
                )
            )
            return

        # Validate via ThemeDefinition
        try:
            from app.interface.themes.schema import ThemeDefinition
            from app.interface.themes.loader import _theme_dir

            candidates = []
            if isinstance(raw, dict) and "themes" in raw:
                candidates = raw["themes"]
            elif isinstance(raw, list):
                candidates = raw
            else:
                candidates = [raw]

            validated = []
            for item in candidates:
                td = ThemeDefinition.model_validate(item)
                validated.append(td)

            # copy to themes dir
            tdir = _theme_dir()
            if tdir is None:
                raise RuntimeError("No themes dir")
            tdir.mkdir(parents=True, exist_ok=True)
            for td in validated:
                dest = tdir / f"{td.id}.json"
                # write single theme file
                dest.write_text(
                    td.model_dump_json(indent=4), encoding="utf-8"
                )
                _lg.info(f"Imported theme '{td.id}' -> {dest}")

            # reload and refresh dropdown
            from app.interface.themes import reload_user_themes

            reload_user_themes()
            self._refresh_theme_options()
            if validated:
                self._theme_dd.value = validated[-1].id
                self._theme_dd.update()

            self.page.show_dialog(
                SnackBar(
                    content=Text(
                        f"Imported {len(validated)} theme(s)"
                    ),
                    behavior=SnackBarBehavior.FLOATING,
                    bgcolor=Colors.GREEN,
                )
            )
        except Exception as ex:
            _lg.warning(f"Theme import failed: {ex}")
            self.page.show_dialog(
                SnackBar(
                    content=Text(f"Import failed: {ex}"),
                    behavior=SnackBarBehavior.FLOATING,
                    bgcolor=Colors.RED,
                )
            )

    def _show_saved_notice(self) -> None:
        """Show the saved confirmation snack."""
        self.page.show_dialog(
            SnackBar(
                content=Text("Settings saved"),
                behavior=SnackBarBehavior.FLOATING,
                bgcolor=Colors.GREEN,
            )
        )

    def _show_save_error(self) -> None:
        """Show an error snack when persisting the settings fails."""
        self.page.show_dialog(
            SnackBar(
                content=Text("Failed to save settings"),
                behavior=SnackBarBehavior.FLOATING,
                bgcolor=Colors.RED,
            )
        )

    # Private builders ----------------------------------------------

    def _build_overlay(self) -> Stack:
        """Build the overlay stack: blurred backdrop and settings card.

        Returns:
            Stack with the backdrop and the centered settings card.
        """
        return Stack(
            expand=True,
            controls=[
                Container(
                    expand=True,
                    bgcolor=Colors.BLACK54,
                    blur=Blur(24, 24),
                    on_click=self.close_settings,
                ),
                Container(
                    alignment=Alignment.CENTER,
                    content=Container(
                        width=460,
                        margin=Margin.all(24),
                        padding=Padding(
                            top=20, right=20, bottom=20, left=20
                        ),
                        border_radius=12,
                        bgcolor=Colors.SURFACE_CONTAINER_HIGH,
                        clip_behavior=ClipBehavior.HARD_EDGE,
                        content=Column(
                            tight=True,
                            spacing=14,
                            controls=[
                                Row(
                                    alignment=MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=(
                                        CrossAxisAlignment.CENTER
                                    ),
                                    controls=[
                                        Text(
                                            "Settings",
                                            size=18,
                                            weight="w700",
                                        ),
                                        IconButton(
                                            icon=Icons.CLOSE,
                                            icon_size=20,
                                            on_click=self.close_settings,
                                        ),
                                    ],
                                ),
                                Row(
                                    spacing=8,
                                    controls=[
                                        self._build_theme_dd(),
                                        FilledTonalButton(
                                            content="Import",
                                            icon=Icons.FOLDER_OPEN,
                                            on_click=self._on_import_theme,
                                        ),
                                        self._build_mode_dd(),
                                    ],
                                ),
                                self._build_log_lvl_dd(),
                                self._build_api_key_field(),
                                self._build_port_field(),
                                self._build_check_updates_sw(),
                                self._build_prereleases_sw(),
                                Text(
                                    "Mode, log level and port are "
                                    "applied after a restart",
                                    size=11,
                                    color=Colors.ON_SURFACE_VARIANT,
                                ),
                                Row(
                                    alignment=(
                                        MainAxisAlignment.SPACE_BETWEEN
                                    ),
                                    vertical_alignment=(
                                        CrossAxisAlignment.CENTER
                                    ),
                                    controls=[
                                        Text(
                                            f"Version {__version__}",
                                            size=12,
                                            color=(
                                                Colors.ON_SURFACE_VARIANT
                                            ),
                                        ),
                                        Row(
                                            spacing=8,
                                            controls=[
FilledButton(
                                            content="Check for updates",
                                            on_click=self._on_check_updates,
                                        ),
                                                FilledButton(
                                                    content="Save",
                                                    icon=Icons.SAVE,
                                                    on_click=self._on_save,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ),
                ),
            ],
        )

    def _build_theme_dd(self) -> Dropdown:
        """Build the theme selector dropdown.

        Returns:
            Dropdown with all builtin + user themes.
        """
        # Lazy import to avoid circular
        try:
            from app.interface.themes import list_themes

            themes = list_themes()
            sorted_items = sorted(
                themes.items(),
                key=lambda kv: (
                    0 if kv[1].is_builtin else 1,
                    kv[1].name.lower(),
                ),
            )
            options = [
                DropdownOption(key=tid, text=td.name)
                for tid, td in sorted_items
            ]
        except Exception:
            options = [
                DropdownOption(key="dark_default", text="Dark"),
                DropdownOption(key="light_default", text="Light"),
            ]
        self._theme_dd = Dropdown(
            label="Theme",
            expand=True,
            value=config.data.THEME,
            options=options,
        )
        return self._theme_dd

    def _build_mode_dd(self) -> Dropdown:
        """Build the application mode dropdown.

        Returns:
            Dropdown with the dev and prod mode options.
        """
        self._mode_dd = Dropdown(
            label="Mode",
            expand=True,
            value=config.data.MODE,
            options=[
                DropdownOption(key="dev", text="Dev"),
                DropdownOption(key="prod", text="Prod"),
            ],
        )
        return self._mode_dd

    def _build_log_lvl_dd(self) -> Dropdown:
        """Build the log level dropdown.

        Returns:
            Dropdown with the supported log levels.
        """
        self._log_lvl_dd = Dropdown(
            label="Log level",
            value=config.data.LOG_LVL,
            options=[
                DropdownOption(key=level, text=level)
                for level in _LOG_LEVELS
            ],
        )
        return self._log_lvl_dd

    def _build_api_key_field(self) -> TextField:
        """Build the Wallhaven API key input.

        Returns:
            Masked text field with a reveal toggle.
        """
        self._api_key_field = TextField(
            label="API key",
            hint_text="Required for NSFW / favorites",
            password=True,
            can_reveal_password=True,
            value=config.data.APIK,
        )
        return self._api_key_field

    def _build_port_field(self) -> TextField:
        """Build the server port input.

        Returns:
            Text field accepting a numeric port value.
        """
        self._port_field = TextField(
            label="Port",
            hint_text="9999",
            value=str(config.data.PORT),
        )
        return self._port_field

    def _build_check_updates_sw(self) -> Switch:
        """Build the startup update check toggle.

        Returns:
            Switch bound to CHECK_UPDATES.
        """
        self._check_updates_sw = Switch(
            label="Check for updates on startup",
            value=config.data.CHECK_UPDATES,
        )
        return self._check_updates_sw

    def _build_prereleases_sw(self) -> Switch:
        """Build the pre-release toggle.

        Returns:
            Switch bound to CHECK_PRERELEASES.
        """
        self._prereleases_sw = Switch(
            label="Offer pre-releases as updates",
            value=config.data.CHECK_PRERELEASES,
        )
        return self._prereleases_sw