# Night Run 3: Domain-Neutral Core + Voting Rules + Scale

Night run 3 completed (log: `logs/overnight3.log`, gate: 94 passed, ruff clean).
Jobs: voting-rule sweep (960 cells), template fuzz (5 kinds x 100), ballot fuzz
(2000 vectors), scale stress (500k blocks, 500 tampers, 2000 amendments),
cluster-bootstrap CIs, figures, full test + lint gate.

Coverage: **94%**, **99 tests passing** (94 night-3 gate + 5 `test_verify_block`
added after), ruff clean.

| job | grid | output |
|---|---|---|
| voting rules | 960 runs (3 rules x 4 N x 4 apathy x 20 seeds) | `night3/voting_sweep.csv`, `night2/tab3_voting_rules.md`, `night3/fig6_voting_rules.png` |
| template fuzz | 5 charter kinds x 100 random decisions | `template_fuzz` log lines (0 errors) |
| ballot fuzz | 2000 choice vectors | `ballot_fuzz` determinism + tamper OK |
| scale stress | 500k blocks, tamper fuzz, amendment hammer | `stress.log` |
| CIs | cluster bootstrap, B=10,000, resample=seed | `night2/tab1/2/3_*.md` |

## What the voting-rule sweep actually tested

Club-scale collectives (N in {5,9,15,30}) decide 3-option proposals under
**sincere but bloc-correlated** preferences: each proposal draws one random
"frontrunner" option and every voter backs it (plurality) / approves it plus
sometimes a second option (approval) / votes yes with p=0.6 (binary). An apathy
abstention layer (`p_abstain` in {0, 0.5, 0.8, 0.95}) sits on top. Quorum 50%,
pass rule: binary needs yes-share >= 50%; plurality/approval need a unique
leader (recorded tie = no decision). The engine under test is the shipped
`Collective.propose + evaluate`, not a reimplementation.

Two consequences for reading Table 3 honestly:

1. **Bloc correlation favours plurality.** Because every voter backs the same
   frontrunner, plurality mechanically finds a unique leader (tie rate 0.000
   everywhere) and its pass rate equals quorum survival. The sweep therefore
   measures *decisiveness under agreement*, not rule quality under disagreement.
2. **Minority-win is zero by construction for the same reason.** With all
   ballots behind one option, the winner always commands ~100% of cast ballots.
   The metric exists in the CSV for future fragmented-preference runs, but
   Night 3 cannot speak to it.

Citable comparisons (Table 3, 95% cluster-bootstrap CIs, n=80 runs per cell):

| rule | p_abstain=0.5 pass | p_abstain=0.8 pass | tie rate at 0.8 |
|---|---|---|---|
| binary | 0.397 [0.370, 0.424] | 0.015 [0.009, 0.022] | 0.000 |
| plurality | 0.486 [0.459, 0.511] | 0.021 [0.013, 0.030] | 0.000 |
| approval | 0.491 [0.463, 0.518] | 0.018 [0.011, 0.026] | 0.179 [0.153, 0.204] |

Reading: at moderate apathy, plurality/approval decide ~9 points more often
than binary (they need a leader, not a 50% yes-share); at high apathy all three
collapse together (turnout ~0.2, quorum does the killing -- the Night 1/2
finding reproduced under a third regime). Approval's cost is the tie column:
0.179 at p_abstain=0.8 rising to 0.209 at 0.95. A tie is a recorded
non-decision requiring a revote, so approval trades decisiveness for
expressiveness in thin quorums.

**Design implication (provisional, pending fragmented-preference runs):**
plurality is the pragmatic club default (decisive, tie-free under agreement);
approval is the expressive option where revote cost is low; binary stays the
ratification rule for yes/no questions. No rule changes the binding constraint:
turnout. Quorum 50 / pass 50 stand.

## Integrity and performance at 500k-block scale (`stress.log`)

Tamper fuzz now runs O(1) per iteration via `Collective.verify_block(idx)`
(recompute block hash + check `prev_hash` linkage to both neighbours +
charter-hash binding), anchored by a full-chain `verify()` before and after
so coverage is not weakened. `tests/test_verify_block.py` (5 tests) proves
the two verifiers agree on 200 seeded tampers. **500/500 tampers caught**,
closing anchor `verify()` True after restore. Night-4 note: with O(1) fuzz
the 500-iteration loop is seconds, not ~20h.

Scale numbers (`stress.log`). In the base
governance sweep, where every member always votes, **quorum and pass thresholds
have no effect at all** — pass rate is 0.74 at every quorum setting (see the flat
`tab1_quorum_pathologies.md`; that flatness is a true result, not a bug, because
a fully-mobilised membership always clears any quorum you set).

Once you model the realistic condition — members who abstain — the picture
inverts (`tab3_apathy_quorum.md`):

- The binding constraint at **every** collective size from 3 to 51 members is
  **turnout/quorum**, not disagreement.
- At `apath_frac=0.5, p_abstain=0.95`, a 50% quorum already fails **30.4%** of
  proposals before they reach a decision. At `apath_frac=0.7`, quorum failure
  hits **97.4%**.
- **Raising the quorum buys paralysis, not legitimacy.** At 75% quorum with
  `apath_frac=0.5`, the pass rate collapses from 68.8% (at 50%) to 8.0%. The
  failure mode shifts from *deadlock* (a decision was taken, it lost) to
  *quorum-fail* (no decision was taken at all) — strictly worse, because the
  collective cannot even register a position.
- Deadlock (ballots cast, threshold unmet) never exceeds ~18% and *falls* as
  apathy rises, because apathy removes the marginal voters who break ties.

**Design implication, validated:** the answer to low turnout is *gasless voting
and liquid (delegated) voting to lower the cost of participation* — not a lower
democratic bar. Recommend shipping `quorum_pct=50, pass_pct=50` as charter
defaults and treating any proposal to raise them as a red flag.

## Payroll: the stable base is the anti-precarity lever

Pooled across 8,910 runs (this is the pilot module only — it is plugged in, not
hardcoded into core):

| policy | mean Gini of payouts |
|---|---|
| `equal` | 0.000 |
| `seniority` | 0.044 |
| `labor_hours` | 0.162 |

Gini falls monotonically in `stable_base_share`, 0.138 at 0.0 to 0.000 at 1.0 —
a clean linear equalisation dial. Recommend keeping `stable_base_share=0.5` as
the default: it halves inequality while still rewarding contribution, and it is
the direct answer to Merk et al.'s (2026) precarity finding.

## Mandates: one honest caveat

The mandate sweep **cannot** answer "does rotation stop a boss re-emerging" as
currently written. `run_mandate_cell` picks the assignee with `rng.choice(addrs)`
on every round, independently of `term_blocks`, so the HHI concentration metric
is flat across all term lengths **by construction**. That flatness is a modelling
artefact, not a finding, and should not be cited.

What the sweep does establish:

- HHI tracks `1/n` (n=5: 0.228 vs 0.200; n=51: 0.053 vs 0.020) — random
  assignment gives sampling noise above the uniform floor and nothing more.
- `n_lapsed` scales correctly with term: 30/30 at `term=1` down to 11/30 at
  `term=20` — expiry logic works.

**To make this a real result** the sim needs an incumbency advantage (e.g.
assignees get re-nominated with probability `p`) so rotation has something to
counteract. That is a follow-up, not something the night run could salvage.

## Integrity and performance (`stress.log`)

- 50,000 blocks appended in 22.9s (~2,180 blocks/s).
- `verify()` over all 50,000 blocks: True in 12.3s.
- `audit_trail()`: 0.2s.
- **Tamper fuzz: 1,000/1,000 mutations caught.** A single flipped byte in any
  stored ballot or hash is detected.
- Amendment hammer: 5,000 attempts, 2,162 rejected, **immutable core intact**
  (`one_worker_one_vote=True`, `stakes_transferable=False`).

So the three contract invariants hold under adversarial load at 50k-block scale.

## Known issues found during recovery

1. `sweep.py` state keys collide between smoke tests and full runs, which
   truncated `gov_sweep.csv`. Fixed by restoring from the auto-backup and
   deduping (8,400 rows now complete).
2. Two aggregation queries initially read non-existent column names
   (`mandate_concentration`, `floor_violation`) and silently returned zeros. The
   real columns are `hhi_concentration` and `floor_violation_rate`. Corrected
   above.
3. `floor_violation_rate` is 0.0000 for every policy — the floor is never
   violated because the base share is distributed before any variable
   allocation. That is correct behaviour, but it makes the metric non-
   discriminating; it should either assert a floor explicitly or be dropped.

## Recommended next steps

1. Rewrite `run_mandate_cell` with an incumbency advantage, re-run the mandate
   sweep (cheap, ~10 min).
2. Add liquid delegation to `governance_sim.py` and re-test the apathy finding —
   the claim "delegation fixes turnout" is currently untested.
3. Make `floor_violation_rate` meaningful or remove it.
4. Write these results into `docs/` as the charter-defaults rationale.
