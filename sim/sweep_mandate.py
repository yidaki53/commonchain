"""Mandate incumbency sweep.

Night 1's ``run_mandate_cell`` picked each assignee with ``rng.choice(addrs)``,
independent of ``term_blocks``. That makes HHI flat across term lengths *by
construction* -- random assignment has nothing for rotation to counteract, so
the sweep could not answer whether rotation stops a boss re-emerging.

This version adds ``p_incumbent``: with that probability the current mandate
holder is re-nominated. Now term length has something to bite on, and the
HHI-vs-term relationship becomes interpretable. Night 1's result stands as
flagged (not citable); this run either replaces it or confirms it.
"""

from __future__ import annotations

import csv
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commonchain.chain import Collective  # noqa: E402
from commonchain.governance import Ballot  # noqa: E402
from commonchain.models import Charter, Member  # noqa: E402

OUT = ROOT / "results" / "night2" / "mandate_sweep.csv"
STATE = ROOT / "results" / "night2" / "mandate_state.json"
FIELDS = [
    "n_members", "term_blocks", "p_incumbent", "seed",
    "n_granted", "hhi_concentration", "max_holder_share", "n_lapsed",
]


def run_cell(
    n_members: int,
    term_blocks: int,
    p_incumbent: float,
    seed: int,
    n_rounds: int = 200,
) -> dict:
    """One mandate-rotation cell.

    ``n_rounds`` defaults to 200 rather than 30 so that long terms are
    distinguishable: with one proposal per round, a term of 20 blocks outlives a
    30-round simulation and terms >= 2 collapse to the same behaviour. 200 rounds
    lets term=1..20 occupy genuinely different portions of the horizon.
    """
    import random

    rng = random.Random(seed)
    charter = Charter.model_validate(
        {"name": "sim", "mission": "mandate rotation", "quorum_pct": 50.0}
    )
    members = [Member(address=f"0x{i:04x}") for i in range(n_members)]
    col = Collective.from_charter(charter, members)
    addrs = [m.address for m in col.active_members()]

    holder_counts = {a: 0 for a in addrs}
    current: str | None = None
    n_granted = n_lapsed = 0

    for round_idx in range(n_rounds):
        height = len(col.chain)
        # An expired holder is no longer the incumbent. Without this check,
        # term_blocks could not affect who holds power at all -- it would only
        # move the lapse counter, leaving HHI flat across term lengths for a
        # reason unrelated to rotation. This is the mechanism term length is
        # supposed to test.
        if current is not None:
            still_holds = any(
                m["assignee"] == current and m["expires_at_block"] > height
                for m in col.active_mandates()
            )
            if not still_holds:
                current = None

        # Incumbency advantage: an unexpired holder is often re-nominated. This
        # is the mechanism rotation exists to counter, so it must be modelled.
        if current is not None and rng.random() < p_incumbent:
            assignee = current
        else:
            assignee = rng.choice(addrs)

        voters = rng.sample(addrs, k=max(1, int(len(addrs) * 0.7)))
        ballots = [Ballot(voter=a, yes=True) for a in voters]
        try:
            block = col.propose(
                "mandate", ballots, kind="mandate",
                payload={
                    "assignee": assignee, "role": "facilitator",
                    "scope": "coordination", "term_blocks": term_blocks,
                },
            )
        except Exception:
            continue
        if block.tally.passed:
            n_granted += 1
            holder_counts[assignee] += 1
            current = assignee
        n_lapsed += sum(
            1 for m in col.mandates
            if m["expires_at_block"] == len(col.chain)
        )

    total = sum(holder_counts.values()) or 1
    hhi = sum((c / total) ** 2 for c in holder_counts.values())
    return {
        "n_members": n_members,
        "term_blocks": term_blocks,
        "p_incumbent": p_incumbent,
        "seed": seed,
        "n_granted": n_granted,
        "hhi_concentration": round(hhi, 6),
        # Largest single member's share of all granted mandates: the plain-
        # language "did one person become the boss" number.
        "max_holder_share": round(max(holder_counts.values()) / total, 4),
        "n_lapsed": n_lapsed,
    }


def grid(seeds: int) -> list[dict]:
    cells = []
    for n, term, p in itertools.product(
        [5, 15, 51], [1, 2, 3, 5, 10, 20], [0.0, 0.2, 0.4, 0.6]
    ):
        for s in range(seeds):
            cells.append(
                {"n_members": n, "term_blocks": term,
                 "p_incumbent": p, "seed": s}
            )
    return cells


def key(c: dict) -> str:
    return f"{c['n_members']}/{c['term_blocks']}/{c['p_incumbent']}/{c['seed']}"


def main() -> None:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cells = grid(seeds)
    done: set[str] = set()
    if STATE.exists():
        done = set(json.loads(STATE.read_text()).get("mandate_done", []))
    fresh = [c for c in cells if key(c) not in done]
    fresh = fresh[: int(sys.argv[2])] if len(sys.argv) > 2 else fresh
    print(f"[mandate2] {len(cells)} cells, {len(done)} done, {len(fresh)} fresh",
          flush=True)

    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if OUT.stat().st_size == 0:
            w.writeheader()
        for i, c in enumerate(fresh):
            try:
                row = run_cell(**c)
            except Exception as e:
                print(f"[mandate2] cell failed {c}: {e}", flush=True)
                continue
            w.writerow(row)
            f.flush()
            done.add(key(c))
            if (i + 1) % 200 == 0:
                STATE.write_text(json.dumps({"mandate_done": sorted(done)}))
                print(f"[mandate2] {i + 1}/{len(fresh)}", flush=True)
    STATE.write_text(json.dumps({"mandate_done": sorted(done)}))
    print(f"[mandate2] done. rows in {OUT}", flush=True)


if __name__ == "__main__":
    main()
