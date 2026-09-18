"""Botón de menú para sidebar/acciones, con hover y cursor hand."""

try:
    from kivy.core.window import Window
    from kivy.properties import BooleanProperty, StringProperty
    from kivy.uix.button import Button

    class MenuButton(Button):
        icon_path = StringProperty("")
        hovered = BooleanProperty(False)

        def __init__(self, **kwargs):
            self.icon_path = kwargs.pop("icon_path", "") or ""
            kwargs.setdefault("size_hint_y", None)
            kwargs.setdefault("height", 44)
            kwargs.setdefault("halign", "center")
            kwargs.setdefault("valign", "middle")
            super().__init__(**kwargs)
            self.bind(size=self._sync_text_size)
            self._sync_text_size()
            Window.bind(mouse_pos=self._on_mouse_pos)

        def _sync_text_size(self, *_args):
            self.text_size = self.size

        def _on_mouse_pos(self, _window, pos):
            if not self.get_root_window():
                return
            inside = self.collide_point(*self.to_widget(*pos))
            if inside and not self.hovered:
                self.hovered = True
                Window.set_system_cursor("hand")
            elif not inside and self.hovered:
                self.hovered = False
                Window.set_system_cursor("arrow")

except ImportError:  # pragma: no cover - entorno sin Kivy

    class MenuButton:  # type: ignore[no-redef]
        pass
