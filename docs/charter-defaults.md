# Charter defaults rationale (simulation-validated)

Why the template charters ship `quorum_pct=50, pass_pct=50`,
`voting_rule=plurality` for clubs. Sources: `results/OVERNIGHT_FINDINGS.md`,
`results/night2/tab1_quorum_pathologies.md` (Table 1, cluster-bootstrap 95%
CIs, 1296 runs), `results/night2/tab2_pass_threshold.md` (Table 2),
`results/night2/tab3_voting_rules.md` (Table 3, 960 runs).

## Quorum 50 / pass 50

Turnout, not thresholds, is the binding constraint. At `apath_frac=0.7`,
quorum failure hits 97.4% -- proposals never reach a decision. Raising quorum
from 50 to 75 collapses the pass rate from 68.8% to 8.0% and shifts the
failure mode from deadlock (a decision happened: no) to quorum-fail (no
decision at all). Raising quorum buys paralysis, not legitimacy.

The fix for low turnout is gasless + liquid delegated voting (lower the cost
of participation), not a lower democratic bar. Treat any proposal to raise
quorum/pass thresholds as a red flag.

## Voting rule: plurality for clubs, binary for ratification

At moderate apathy (`p_abstain=0.5`), plurality/approval decide ~9 points more
often than binary (0.49 vs 0.40 -- they need a unique leader, not a 50%
yes-share). At high apathy all three collapse together: quorum does the
killing regardless of rule. Approval's cost is ties: 0.18 at `p_abstain=0.8`,
0.21 at 0.95 -- a recorded non-decision requiring a revote.

Defaults: `plurality` where decisiveness matters (clubs, elections),
`approval` where expressiveness is worth revote cost, `binary` for yes/no
ratification. Caveat: the sweep used bloc-correlated sincere preferences, so
minority-win rates are zero by construction -- fragmented-preference runs are
still open work.

## Stable base for payroll co-ops

`stable_base_share=0.5`: Gini falls monotonically 0.138 at 0.0 to 0.000 at
1.0. Half halves inequality while still rewarding contribution (answer to
Merk et al. 2026 precarity finding). Module only -- parties, movements and
clubs do not enable it.

## Scale claim

500k-block chain: append ~1400/s, full `verify()` ~150s, `audit_trail()` ~4s,
500/500 seeded tampers caught (O(1) `verify_block`, anchored by full verify
pre/post), 2000 charter amendments with immutable core intact.
