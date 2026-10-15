"""Shared fixtures: a 3-person collective with a standard charter."""

from __future__ import annotations

import pytest

from commonchain.chain import Collective
from commonchain.governance import Ballot
from commonchain.models import Charter, Member


@pytest.fixture
def charter() -> Charter:
    return Charter.model_validate(
        {
            "name": "Test Collective",
            "mission": "Workers own the means of production.",
            "kind": "coop",
            "quorum_pct": 50.0,
            "pass_pct": 50.0,
            "supermajority_pct": 66.0,
            "modules": {"payroll": {"policy": "equal", "stable_base_share": 0.5}},
        }
    )


@pytest.fixture
def members() -> list[Member]:
    return [
        Member(address="0xaaa", display_name="Alice", metrics={"labor_hours": 10}),
        Member(address="0xbbb", display_name="Bob", metrics={"labor_hours": 20}),
        Member(address="0xccc", display_name="Cara", metrics={"labor_hours": 5}),
    ]


@pytest.fixture
def collective(charter: Charter, members: list[Member]) -> Collective:
    return Collective.from_charter(charter, members)


def yes(*addrs: str) -> list[Ballot]:
    return [Ballot(voter=a, yes=True) for a in addrs]


def no(*addrs: str) -> list[Ballot]:
    return [Ballot(voter=a, yes=False) for a in addrs]
