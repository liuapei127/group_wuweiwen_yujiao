"""Transport-independent errors raised by application services."""

class BusinessError(Exception):
    def __init__(self, status_code: int, detail: str, *, envelope: bool = False):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.envelope = envelope


class CommandError(BusinessError):
    def __init__(self, message: str, code: int):
        super().__init__(code, message, envelope=True)
