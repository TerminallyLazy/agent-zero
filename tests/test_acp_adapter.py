"""Tests for ACP adapter module."""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_acp_availability_check():
    """Test ACP availability reflects actual SDK state."""
    from python.helpers import acp_adapter

    result = acp_adapter.is_available()
    assert isinstance(result, bool)


def test_acp_adapter_module_imports():
    """Test that the acp_adapter module can be imported without errors."""
    from python.helpers import acp_adapter

    assert hasattr(acp_adapter, "AgentZeroACP")
    assert hasattr(acp_adapter, "is_available")
    assert hasattr(acp_adapter, "ACP_AVAILABLE")
