from flet import Container, Colors, Alignment, Text


class RightPanel(Container):
    def __init__(self) -> None:
        super().__init__()
        self.expand = 1
        self.bgcolor = Colors.DEEP_PURPLE_500
        self.alignment = Alignment.CENTER
        self.content = Text("1")
