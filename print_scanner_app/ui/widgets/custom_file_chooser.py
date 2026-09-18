"""Selector de archivos simple para Kivy (fallback sin Kivy)."""

try:
    from kivy.uix.filechooser import FileChooserListView

    class CustomFileChooser(FileChooserListView):
        pass

except ImportError:  # pragma: no cover

    class CustomFileChooser:  # type: ignore[no-redef]
        pass
