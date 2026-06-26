"""Suite/dataset provenance hashing (#11)."""

from agenteval.models import EvalCase, EvalSuite
from agenteval.provenance import suite_content_hash


def _case(name="c1", expected=None, grader="exact"):
    return EvalCase(name=name, input="hi", expected=expected or {"value": "ok"}, grader=grader)


def _suite(cases=None, name="s", agent="a", defaults=None):
    return EvalSuite(name=name, agent=agent, cases=cases or [_case()], defaults=defaults or {})


def test_hash_is_sha256_prefixed_and_reproducible():
    s = _suite()
    h1 = suite_content_hash(s)
    h2 = suite_content_hash(_suite())  # rebuilt identical
    assert h1.startswith("sha256:")
    assert h1 == h2


def test_hash_changes_when_a_case_changes():
    base = suite_content_hash(_suite([_case(expected={"value": "ok"})]))
    changed = suite_content_hash(_suite([_case(expected={"value": "DIFFERENT"})]))
    assert base != changed


def test_hash_changes_on_case_reorder():
    a = suite_content_hash(_suite([_case("c1"), _case("c2")]))
    b = suite_content_hash(_suite([_case("c2"), _case("c1")]))
    assert a != b  # order-sensitive


def test_hash_changes_on_name_agent_defaults():
    base = suite_content_hash(_suite())
    assert suite_content_hash(_suite(name="other")) != base
    assert suite_content_hash(_suite(agent="other")) != base
    assert suite_content_hash(_suite(defaults={"timeout": 5})) != base


def test_command_registered():
    from click.testing import CliRunner

    from agenteval.cli import cli

    res = CliRunner().invoke(cli, ["suite-hash", "--help"])
    assert res.exit_code == 0
    assert "content-hash" in res.output.lower()
