class AppError(Exception):
    def __init__(self, code: str, status: int, message: str, request_id: str | None = None):
        self.code = code
        self.status = status
        self.message = message
        self.request_id = request_id
        super().__init__(message)
