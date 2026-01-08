"""Tests for ACP adapter module."""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_acp_availability_check_when_installed():
    """Test that ACP availability returns True when acp package is installed."""
    from python.helpers import acp_adapter

    # When acp is installed, is_available should return True
    result = acp_adapter.is_available()

    assert result is True


def test_acp_adapter_module_imports():
    """Test that the acp_adapter module can be imported without errors."""
    from python.helpers import acp_adapter

    assert hasattr(acp_adapter, "AgentZeroACP")
    assert hasattr(acp_adapter, "is_available")
    assert hasattr(acp_adapter, "ACP_AVAILABLE")
