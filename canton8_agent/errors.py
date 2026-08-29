"""Explicit failure categories used by safe charge orchestration."""


class AgentError(RuntimeError):
    """A terminal policy, resolution, approval, or submission failure."""


class ResolutionError(AgentError):
    """The resolver could not produce compatible direct-settlement inputs."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class SubmissionError(AgentError):
    """A ledger submission failed, with retry semantics made explicit."""

    def __init__(self, message: str, *, retryable: bool, ambiguous: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.ambiguous = ambiguous
