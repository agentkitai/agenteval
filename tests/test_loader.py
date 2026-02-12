"""Tests for agenteval.loader."""

import os

import pytest

from agenteval.loader import LoadError, load_suite

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_load_valid_suite():
    suite = load_suite(os.path.join(FIXTURES, "valid_suite.yaml"))
    assert suite.name == "test-suite"
    assert suite.agent == "myapp.agent:run"
    assert len(suite.cases) == 2


def test_defaults_applied():
    suite = load_suite(os.path.join(FIXTURES, "valid_suite.yaml"))
    # First case should inherit default grader
    assert suite.cases[0].grader == "contains"
    assert suite.cases[0].grader_config == {"case_sensitive": False}


def test_case_overrides_defaults():
    suite = load_suite(os.path.join(FIXTURES, "valid_suite.yaml"))
    # Second case overrides grader and grader_config
    assert suite.cases[1].grader == "exact"
    # Should merge: default case_sensitive + override strip
    assert suite.cases[1].grader_config == {"case_sensitive": False, "strip": True}


def test_missing_name():
    with pytest.raises(LoadError, match="'name'"):
        load_suite(os.path.join(FIXTURES, "missing_name.yaml"))


def test_missing_cases():
    with pytest.raises(LoadError, match="'cases'"):
        load_suite(os.path.join(FIXTURES, "missing_cases.yaml"))


def test_empty_cases():
    with pytest.raises(LoadError, match="non-empty"):
        load_suite(os.path.join(FIXTURES, "empty_cases.yaml"))


def test_invalid_grader():
    with pytest.raises(LoadError, match="invalid grader"):
        load_suite(os.path.join(FIXTURES, "invalid_grader.yaml"))


def test_bad_yaml():
    with pytest.raises(LoadError, match="Invalid YAML"):
        load_suite(os.path.join(FIXTURES, "bad_yaml.yaml"))


def test_file_not_found():
    with pytest.raises(LoadError, match="not found"):
        load_suite("/nonexistent/path.yaml")
