"""Settings panel: blurred overlay shown above the whole interface."""

from flet import (
    Alignment,
    Blur,
    ClipBehavior,
    Colors,
    Column,
    Container,
    CrossAxisAlignment,
    FilledButton,
    IconButton,
    Icons,
    MainAxisAlignment,
    Margin,
    Padding,
    Row,
    Stack,
    Text,
)

from app.core.version import __version__
from app.interface.components.update_dialog import check_and_offer


class SettingsPanel(Container):
    """Fullscreen settings overlay with a blurred backdrop.

    The panel is mounted into the page overlay, so it always covers the
    entire interface. It stays hidden until :meth:`open_settings` is
    called from the gear icon in the header bar.
    """

    def __init__(self) -> None:
        super().__init__()
        self.expand = True
        self.visible = False
        self.content = self._build_overlay()

    # Public API ----------------------------------------------------

    def toggle_settings(self, e) -> None:
        """Open or close the settings overlay.

        Args:
            e: Click event from the gear icon.
        """
        self.visible = not self.visible
        self.update()

    def open_settings(self, e) -> None:
        """Show the settings overlay.

        Args:
            e: Click event.
        """
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

    def _on_check_updates(self, e) -> None:
        """Run a manual update check in the background.

        Args:
            e: Click event from the update button.
        """
        self.close_settings(e)
        self.page.run_task(check_and_offer, self.page, True)

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
                        width=420,
                        margin=Margin.all(24),
                        padding=Padding(
                            top=20, right=20, bottom=20, left=20
                        ),
                        border_radius=12,
                        bgcolor=Colors.GREY_900,
                        clip_behavior=ClipBehavior.HARD_EDGE,
                        content=Column(
                            tight=True,
                            spacing=16,
                            controls=[
                                Row(
                                    alignment=MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=CrossAxisAlignment.CENTER,
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
                                Container(
                                    content=Column(
                                        tight=True,
                                        spacing=12,
                                        controls=[
                                            Text(
                                                f"Version {__version__}",
                                                color=Colors.WHITE_54,
                                            ),
                                            FilledButton(
                                                content="Check for updates",
                                                on_click=self._on_check_updates,
                                            ),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ),
                ),
            ],
        )
