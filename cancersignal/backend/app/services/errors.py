class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PipelineError(Exception):
    """A pipeline stage rejected its input/output; never expose clinical text in errors."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
