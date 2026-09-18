from print_scanner_app.application.services.printer_service import PrinterService


def test_connect_no_device(monkeypatch):
    monkeypatch.setattr(
        "print_scanner_app.application.services.printer_service.first_lp_device",
        lambda: None,
    )
    svc = PrinterService()
    assert not svc.connect(retries=None)


def test_move_film_calls_client(monkeypatch):
    svc = PrinterService()

    class FakeClient:
        def __init__(self):
            self.seen = []

        def advance_pixels(self, px):
            self.seen.append(px)

    fc = FakeClient()
    svc._client = fc
    assert svc.move_film(7)
    assert fc.seen == [7]


def test_send_image_calls_client():
    svc = PrinterService()

    class FakeClient:
        def __init__(self):
            self.seen = []

        def send_image(self, img):
            self.seen.append(img)

    fc = FakeClient()
    svc._client = fc
    assert svc.send_image("img1")
    assert fc.seen == ["img1"]
