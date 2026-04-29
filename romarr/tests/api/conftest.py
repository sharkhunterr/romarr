"""Pytest fixtures for the FastAPI app tests.

The shared ``api_engine`` + ``api_client`` fixtures now live in
``tests/conftest.py`` so they can be reused by tests under
``tests/metadata/api/`` without copy-paste. This file is kept so any
future API-specific fixtures (e.g. an ``admin_client`` helper) have a
natural home.
"""

from __future__ import annotations
