from flet import Page, SafeArea, Container, Row

from app.core import get_logger
from app.interface.components import LeftPanel, MiddlePanel, RightPanel

_lg = get_logger()


async def flet_main(page: Page):
    _lg.debug("flet_main called...")

    page.title = "ywallhaven"
    page.padding = 10

    left_panel = LeftPanel()
    middle_panel = MiddlePanel()
    right_panel = RightPanel()

    page.add(
        SafeArea(
            expand=True,
            content=Container(
                border_radius=10,
                content=Row(
                    spacing=8,
                    controls=[left_panel, middle_panel, right_panel],
                ),
            ),
        )
    )
