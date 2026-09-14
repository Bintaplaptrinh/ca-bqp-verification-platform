"""Re-export canonical cases router for modular backward compatibility.

Standard: Quality-first 2026 Production Architecture.
Canonical implementation lives in `cabqp.api.cases`.
"""

from cabqp.api.cases import router

__all__ = ["router"]
