"""Settings panel: blurred overlay shown above the whole interface."""

from typing import Callable

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
    FilledButton,
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
    ThemeMode,
)

from app.core import config
from app.core.version import __version__
from app.interface.components.update_dialog import check_and_offer

_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


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
    ) -> None:
        super().__init__()
        self._on_api_key_change = on_api_key_change
        self.expand = True
        self.visible = False
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
        self.update()

    def open_settings(self, e) -> None:
        """Show the settings overlay.

        Args:
            e: Click event.
        """
        self._sync_from_config()
        self.visible = True
        self.update()

    def close_settings(self, e) -> None:
        """Hide the settings overlay.

        Args:
            e: Click event from the close button or backdrop.
        """
        self.visible = False
        self.update()

    # Event handlers ------------------------------------------------

    def _on_save(self, e) -> None:
        """Validate, persist and apply the edited settings.

        Args:
            e: Click event from the save button.
        """
        api_key = (self._api_key_field.value or "").strip()

        try:
            port = int((self._port_field.value or "").strip() or 0)
        except ValueError:
            self._port_field.error = "Invalid port"
            self._port_field.update()
            return

        old_theme = config.data.THEME
        new_theme = self._theme_dd.value or old_theme

        config.update(
            THEME=new_theme,
            APIK=api_key,
            MODE=self._mode_dd.value or config.data.MODE,
            LOG_LVL=self._log_lvl_dd.value or config.data.LOG_LVL,
            PORT=port,
            CHECK_UPDATES=bool(self._check_updates_sw.value),
            CHECK_PRERELEASES=bool(self._prereleases_sw.value),
        )

        if new_theme != old_theme:
            self.page.theme_mode = (
                ThemeMode.LIGHT if new_theme == "light" else ThemeMode.DARK
            )
            self.page.update()

        if self._on_api_key_change is not None:
            self._on_api_key_change(api_key)

        self._show_saved_notice()

    def _on_check_updates(self, e) -> None:
        """Run a manual update check in the background.

        Args:
            e: Click event from the update button.
        """
        self.close_settings(e)
        self.page.run_task(check_and_offer, self.page, manual=True)

    # Private helpers -----------------------------------------------

    def _sync_from_config(self) -> None:
        """Refresh the panel fields from the current config values."""
        data = config.data
        self._theme_dd.value = data.THEME
        self._api_key_field.value = data.APIK
        self._mode_dd.value = data.MODE
        self._log_lvl_dd.value = data.LOG_LVL
        self._port_field.value = str(data.PORT)
        self._check_updates_sw.value = data.CHECK_UPDATES
        self._prereleases_sw.value = data.CHECK_PRERELEASES

    def _show_saved_notice(self) -> None:
        """Show the saved confirmation snack."""
        self.page.show_dialog(
            SnackBar(
                content=Text("Settings saved"),
                behavior=SnackBarBehavior.FLOATING,
                bgcolor=Colors.GREEN,
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
            Dropdown with the dark and light theme options.
        """
        self._theme_dd = Dropdown(
            label="Theme",
            expand=True,
            value=config.data.THEME,
            options=[
                DropdownOption(key="dark", text="Dark"),
                DropdownOption(key="light", text="Light"),
            ],
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