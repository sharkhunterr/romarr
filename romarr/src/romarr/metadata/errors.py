"""Provider-error hierarchy used by every metadata client.

The aggregator + circuit breaker treat each subclass differently:

  - ``AuthError``        → tripped immediately, never retried (FR-019)
  - ``RateLimitError``   → counts as a transient breaker hit + adds
                            extra back-off
  - ``NotFoundError``    → returned as ``None``; no retry
  - ``TransientError``   → retried by tenacity, then trips breaker
"""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for any failure raised by a provider client."""


class AuthError(ProviderError):
    """Provider rejected the configured credentials (HTTP 401/403)."""


class RateLimitError(ProviderError):
    """Provider returned HTTP 429 or an equivalent quota signal."""


class NotFoundError(ProviderError):
    """Provider returned 404 / empty result for the requested entity."""


class TransientError(ProviderError):
    """Network / 5xx error worth retrying within tenacity's budget."""
