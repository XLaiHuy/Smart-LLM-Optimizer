from app.contracts.dtos import ExecutionRequest, TaskProfile


class UnknownTaskAnalyzer:
    def analyze(self, req: ExecutionRequest) -> TaskProfile:
        return TaskProfile()
