# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for the ``synthadoc workflow`` CLI sub-group."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synthadoc.cli.main import app

runner = CliRunner()


def test_list_workflows_empty_registry():
    """When CLI_REGISTRY is empty, list must print 'No workflows registered.'"""
    with patch("synthadoc.agents.workflows._registry.CLI_REGISTRY", new={}):
        result = runner.invoke(app, ["workflow", "list"])
    assert "No workflows registered." in result.output
