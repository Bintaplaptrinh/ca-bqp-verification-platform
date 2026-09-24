from __future__ import annotations


class DocumentLimitError(ValueError):
    """Permanent, operator-visible document resource limit violation."""

    def __init__(self, code: str, **details):
        self.code = code
        self.details = details
        super().__init__(code)
