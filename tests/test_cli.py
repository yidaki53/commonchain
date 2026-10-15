"""CLI end-to-end tests using typer's CliRunner against a temp directory."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from commonchain.cli import app

runner = CliRunner()


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    """Run all CLI commands inside an isolated temp directory."""

    class _Ctx:
        dir = tmp_path

    monkeypatch.chdir(tmp_path)
    return _Ctx()


def test_init_writes_state(fresh) -> None:
    result = runner.invoke(app, ["init", "--name", "Test Co-op", "--kind", "coop"])
    assert result.exit_code == 0, result.output
    assert "Genesis (charter) hash" in result.output
    state = json.loads((fresh.dir / "collective.json").read_text())
    assert state["charter"]["name"] == "Test Co-op"
    assert state["charter"]["one_member_one_vote"] is True


def test_all_five_kinds_init(fresh) -> None:
    for kind in ("coop", "party", "movement", "club", "generic"):
        result = runner.invoke(app, ["init", "--name", kind.title(), "--kind", kind])
        assert result.exit_code == 0, result.output


def test_unknown_kind_is_rejected(fresh) -> None:
    result = runner.invoke(app, ["init", "--name", "X", "--kind", "bogus"])
    assert result.exit_code != 0


def test_jurisdiction_module_is_applied(fresh) -> None:
    runner.invoke(app, ["init", "--name", "Sveriges Kooperativ", "--kind", "coop",
                        "--jurisdiction", "se"])
    state = json.loads((fresh.dir / "collective.json").read_text())
    assert state["charter"]["jurisdiction_module"] == "se"


def test_full_workflow(fresh) -> None:
    runner.invoke(app, ["init", "--name", "Bright Futures", "--kind", "coop"])
    for addr, name in (("0xaaa", "Alice"), ("0xbbb", "Bob"), ("0xccc", "Cara")):
        r = runner.invoke(
            app, ["member", "add", addr, "--name", name, "--hours", "10"]
        )
        assert r.exit_code == 0, r.output

    listed = runner.invoke(app, ["member", "list"])
    assert "Alice" in listed.output

    r = runner.invoke(
        app,
        ["propose", "Buy a 3D printer", "--yes", "0xaaa,0xbbb", "--no", "0xccc"],
    )
    assert r.exit_code == 0, r.output
    assert "PASSED" in r.output

    r = runner.invoke(app, ["pay", "900"])
    assert r.exit_code == 0, r.output
    assert "300.00" in r.output

    r = runner.invoke(app, ["audit"])
    assert r.exit_code == 0, r.output
    assert "Chain integrity: OK" in r.output


def test_amend_via_cli_changes_policy(fresh) -> None:
    runner.invoke(app, ["init", "--name", "Co", "--kind", "coop"])
    runner.invoke(app, ["member", "add", "0xaaa"])
    runner.invoke(app, ["member", "add", "0xbbb"])
    runner.invoke(app, ["member", "add", "0xccc"])
    r = runner.invoke(
        app,
        [
            "propose",
            "Adopt labour hours",
            "--yes",
            "0xaaa,0xbbb,0xccc",
            "--amend",
            '{"modules.payroll.policy": "labor_hours"}',
        ],
    )
    assert r.exit_code == 0, r.output
    state = json.loads((fresh.dir / "collective.json").read_text())
    assert state["charter"]["modules"]["payroll"]["policy"] == "labor_hours"


def test_onboard_vote_adds_member(fresh) -> None:
    runner.invoke(app, ["init", "--name", "Co", "--kind", "coop"])
    runner.invoke(app, ["member", "add", "0xaaa"])
    runner.invoke(app, ["member", "add", "0xbbb"])
    runner.invoke(app, ["member", "add", "0xccc"])
    r = runner.invoke(
        app,
        ["propose", "Onboard Dana", "--yes", "0xaaa,0xbbb", "--onboard", "0xddd"],
    )
    assert r.exit_code == 0, r.output
    state = json.loads((fresh.dir / "collective.json").read_text())
    assert "0xddd" in state["members"]


def test_mandate_vote_grants_rotating_role(fresh) -> None:
    runner.invoke(app, ["init", "--name", "Co", "--kind", "coop"])
    runner.invoke(app, ["member", "add", "0xaaa"])
    runner.invoke(app, ["member", "add", "0xbbb"])
    runner.invoke(app, ["member", "add", "0xccc"])
    r = runner.invoke(
        app,
        [
            "propose",
            "Alice facilitates next sprint",
            "--yes",
            "0xaaa,0xbbb",
            "--mandate",
            "0xaaa:facilitator",
            "--scope",
            "sprint planning",
            "--term",
            "5",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "PASSED" in r.output
    state = json.loads((fresh.dir / "collective.json").read_text())
    assert len(state["mandates"]) == 1
    assert state["mandates"][0]["role"] == "facilitator"

    listed = runner.invoke(app, ["mandates"])
    assert listed.exit_code == 0, listed.output
    assert "facilitator" in listed.output
    assert "0xaaa" in listed.output


def test_pay_without_payroll_module_fails_cleanly(fresh) -> None:
    """A party has no payroll: `pay` refuses instead of silently splitting."""
    runner.invoke(app, ["init", "--name", "Party", "--kind", "party"])
    runner.invoke(app, ["member", "add", "0xaaa"])
    r = runner.invoke(app, ["pay", "900"])
    assert r.exit_code != 0


def test_export_writes_archive(fresh, tmp_path) -> None:
    runner.invoke(app, ["init", "--name", "Co", "--kind", "coop"])
    out = tmp_path / "archive.json"
    r = runner.invoke(app, ["export", str(out)])
    assert r.exit_code == 0, r.output
    data = json.loads(out.read_text())
    assert "genesis_hash" in data
    assert "charter" in data


def test_commands_without_init_fail_cleanly(fresh) -> None:
    result = runner.invoke(app, ["member", "list"])
    assert result.exit_code != 0
