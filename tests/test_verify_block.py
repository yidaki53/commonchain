"""Agreement between the O(1) verify_block() and the full-chain verify().

verify_block() is what the scale stress fuzz loop calls per tamper; if it
ever disagreed with verify() the 500/500 claim would be hollow.
"""

from __future__ import annotations

import random

from tests.conftest import no, yes


def test_clean_chain_both_pass(collective, members):
    addrs = [m.address for m in members]
    for i in range(5):
        collective.propose(f"p{i}", yes(*addrs))
    assert collective.verify()
    assert all(collective.verify_block(i) for i in range(5))


def test_verify_block_catches_ballot_tamper(collective, members):
    addrs = [m.address for m in members]
    for i in range(5):
        collective.propose(f"p{i}", yes(*addrs))
    b = collective.chain[2]
    b.tally.yes += 99
    assert not collective.verify_block(2)
    assert not collective.verify()


def test_verify_block_catches_hash_tamper(collective, members):
    addrs = [m.address for m in members]
    for i in range(5):
        collective.propose(f"p{i}", yes(*addrs))
    collective.chain[3].block_hash = "ff" * 32
    assert not collective.verify_block(3)
    assert not collective.verify()


def test_verify_block_detects_broken_successor_linkage(collective, members):
    # Tampering block 1 breaks block 2's prev_hash expectation too.
    addrs = [m.address for m in members]
    for i in range(4):
        collective.propose(f"p{i}", yes(*addrs))
    collective.chain[1].block_hash = "ab" * 32
    assert not collective.verify_block(2)


def test_verify_block_agrees_with_verify_on_seeded_tampers(collective, members):
    addrs = [m.address for m in members]
    for i in range(12):
        collective.propose(f"p{i}", (yes if i % 2 == 0 else no)(*addrs))
    rng = random.Random(7)
    for _ in range(200):
        idx = rng.randrange(len(collective.chain))
        b = collective.chain[idx]
        saved_yes, saved_hash = b.tally.yes, b.block_hash
        if rng.random() < 0.5:
            b.tally.yes = saved_yes + 99
        else:
            b.block_hash = "ff" * 32
        assert collective.verify_block(idx) == collective.verify()
        b.tally.yes, b.block_hash = saved_yes, saved_hash
    assert collective.verify()
