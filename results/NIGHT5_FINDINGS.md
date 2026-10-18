# Night Run 5: Fragmentation + Capture + Aligned Delegation + Verify Scaling

Night run 5 completed (log: `logs/overnight5.log`, gate: 99 passed, ruff clean).
Jobs: fragmentation sweep (9720 cells), capture/amendment sweep (2700 cells),
deleg-blocs sweep (1620 cells), verify bench (L=1k..25k), Tables 5-9 with
cluster-bootstrap CIs, Figs 8-10, mlflow-lite log, full test + lint gate.

| job | grid | output |
|---|---|---|
| fragmentation | 9720 cells (3 rules x 3 blocs x 3 noise x 3 abstain x 3 N x 30 seeds) | `night5/fragmentation_sweep.csv`, `tab5_fragmentation.md`, `fig8_fragmentation.png` |
| capture | 2700 cells (2 N x 3 super x 5 hostile x 3 turnout x 30 seeds) | `night5/amendment_sweep.csv`, `tab6_capture.md`, `fig9_capture.png` |
| deleg-blocs | 1620 cells (3 abstain x 3 rate x 3 aligned x 2 depth x 30 seeds) | `night5/deleg_blocs_sweep.csv`, `tab7_deleg_blocs.md` |
| verify bench | L in {1000,5000,10000,25000} | `night5/verify_bench.csv`, `fig10_verify_scaling.png` |
| CI upgrades | night-2 mandate (3600) + delegation (1800) with CIs | `tab8_mandate_ci.md`, `tab9_delegation_ci.md` |

Coverage: 14,040 new cells + 5,400 re-analysed with CIs. All chains verified
(`chain_ok` 2700/2700 in capture; fragmentation/deleg run on real engine).

## Voting rules under fragmented preferences (Table 5, Fig 8)

Night 3's `minority_win_rate ~ 0` was by construction -- uniform-random
favorites mean no coherent minority exists. Night 5 fixes it with
bloc-structured sincere preferences (bloc 0 = targeted minority).

Pooled summary (9720 cells):

| rule | minority-win | tie | satisfaction |
|---|---|---|---|
| binary | 0.000 | 0.000 | 0.272 |
| plurality | 0.428 | 0.247 | 0.357 |
| approval | 0.499 | 0.251 | 0.561 |

Binary cannot produce a minority win by construction (pass needs >=50% of
cast) -- the citable contrast. Plurality and approval both decide via unique
leader + quorum, so under fragmentation ~43-50% of their decisions are won by
a bloc with <50% of cast ballots. Approval pays the same tie price as
plurality (~0.25) but buys decisively higher satisfaction (0.561 vs 0.357):
its ballots carry more preference information, so more voters see their bloc
win something.

Design implication: plurality is the decisive default only under agreement
(Night 3); under disagreement both multi-option rules routinely crown
minorities. If legitimacy requires majority support, binary ratification or a
majority-plus-runoff is the honest rule; if expressiveness matters, approval
dominates plurality on satisfaction at equal tie cost. No rule escapes the
turnout constraint (abstain=0.8 collapses all pass rates to ~0.005).

## Constitutional capture of the amendable layer (Table 6, Fig 9)

`stress.py` hammered only the immutable core. Night 5 attacks the amendable
layer the way a real adversary would: a disciplined bloc proposes 'lower
supermajority to 50' until it passes; an engaged honest majority (turnout 0.8)
then tries to restore. All 2700 chains verify after every round.

Threshold behaviour is sharp (turnout=0.2 slice):

| hostile | capture rate |
|---|---|
| 0.30 | 0.000 |
| 0.34 | 0.333 |
| 0.40 | 1.000 |

At hostile=0.5 capture is immediate (first-capture round ~0.0-0.1) and
restoration is 0.000 -- the bloc governs alone. At hostile=0.34/supermajority
60/N=15 capture takes ~3.8 rounds with restoration ~6.5 rounds: the window
where defence is possible but slow. Raising supermajority to 75 pushes the
capture frontier from 0.34 to 0.40 (N=51 slice), quantifying what the bar buys.

Design implication: the immutable-core/amendable-policy split survives honest
disagreement but not a disciplined 40% minority under low honest turnout. The
defence is turnout, not a higher number on paper: at honest turnout 0.8,
capture at hostile=0.4 falls to 0.10 (super 66) / 0.00 (super 75). Ship
supermajority 66 as default; monitor turnout as the security metric.

## Delegation: aligned (chosen) vs random (Table 7)

Night 2's map picks delegates uniform-random. Real liquid democracy is chosen.
`aligned_frac` = P(delegator picks own-bloc delegate).

| aligned | delta pass (delegated - baseline) | fidelity |
|---|---|---|
| 0.0 (night-2 model) | +0.037 | 0.016 |
| 1.0 (fully aligned) | +0.080 | 1.000 |

Aligned delegation more than doubles the turnout benefit (+0.080 vs +0.037)
because carried ballots land where the delegator would have voted anyway --
fidelity 1.0 vs 0.016. Random delegation rescues quorum mechanically; aligned
delegation rescues it faithfully. Depth 3 vs 1 changes little at aligned=1.0.

Caveat (held from night 2, now quantified): max delegate share at
aligned=1.0/depth=3 reaches ~0.35 -- concentration is the price. Delegate
weight stays exactly 1, so this is agenda influence, not plutocracy.

## Verify scaling (Fig 10, `verify_bench.csv`)

| L | verify full us/block | verify_block us | append blocks/s |
|---|---|---|---|
| 1000 | 322.1 | 310.3 | 1791.6 |
| 5000 | 281.2 | 363.5 | 1433.1 |
| 10000 | 279.9 | 327.5 | 1462.0 |
| 25000 | 266.6 | 227.4 | 1150.3 |

`verify()` is linear O(n) at ~270-320 us/block (6.67s at 25k blocks);
`verify_block()` is flat O(1) at ~230-360 us. The fuzz strategy (full anchor
+ O(1) per-tamper + closing anchor) is the only affordable shape at scale --
confirmed empirically, not asserted.

## CI upgrades: Tables 8-9

Night-2 mandate/delegation tables were point estimates. Both now carry
cluster-bootstrap 95% CIs (resample = seed), making them citable:

- Table 8 (mandate, 3600 runs): max-holder share rises in `p_incumbent`
  (n=5: 0.297 [0.283,0.311] at 0.0 -> 0.393 [0.371,0.417] at 0.6) while flat
  across term lengths -- term length as implemented does not counteract
  incumbency because mandates overlap rather than queue. Honest null, now
  with intervals.
- Table 9 (delegation, 1800 runs): delta-pass effects survive CIs where they
  matter (e.g. n=51/apath 0.7/p_abstain 0.8/rate 0.5/depth 3:
  +0.418 [0.335,0.497], q-fail 0.915 -> 0.425). Small-N cells straddle zero
  and are reported as such.

## Determinism and provenance

- Sweeps deterministic given seeds; state files isolate night-5 from smoke
  (`*_smoke.csv` never touched by full grids).
- Citable artifacts: `night5/tab5_fragmentation.md` (Table 5),
  `night5/tab6_capture.md` (Table 6), `night5/tab7_deleg_blocs.md` (Table 7),
  `night5/tab8_mandate_ci.md` (Table 8), `night5/tab9_delegation_ci.md`
  (Table 9), `night5/fig8_fragmentation.png`, `night5/fig9_capture.png`,
  `night5/fig10_verify_scaling.png`, `night5/mlruns/`.
- Gate: 99 passed, ruff clean (log: `99 passed in 25.29s`).

## Next steps

1. Fragmentation uses sincere bloc voting -- strategic voting (bullet voting
   under approval, spoiler entry under plurality) untested.
2. Capture sweep restores with honest turnout 0.8 -- models recovery capacity,
   not recovery will. A demoralised majority staying home is the darker case.
3. `satisfaction` = share of cast ballots on winning side -- a
   turnout-weighted legitimacy (share of eligible satisfied) would be stricter.
4. Keep `results/night5/` immutable; new arms go to isolated files.

