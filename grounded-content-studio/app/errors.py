class ResearchError(RuntimeError):
    """The website could not be read or yielded no usable pages."""


class LLMUnavailableError(RuntimeError):
    """Every configured LLM provider failed to produce valid content."""

    def __init__(self, reasons: dict[str, str]):
        self.reasons = reasons
        detail = ", ".join(f"{provider}={reason}" for provider, reason in reasons.items())
        super().__init__(f"All LLM providers failed ({detail}).")
