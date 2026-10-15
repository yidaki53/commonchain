# Table 3: Apathy, Turnout and the Quorum Constraint

Simulation of a collective whose members abstain at rate `p_abstain` (a fraction `apath_frac` of members are structurally apathetic). This is the realistic condition of a large party or movement, and it is the case the chain cannot fix by itself.

## 3a: Turnout vs quorum threshold (all scales pooled)

| quorum | apath_frac | p_abstain | mean turnout | pass rate | quorum-fail | deadlock |
|---|---|---|---|---|---|---|
| 50% | 0.2 | 0.80 | 82.1% | 83.3% | 0.0% | 16.7% |
| 50% | 0.2 | 0.95 | 78.6% | 83.7% | 0.0% | 16.3% |
| 50% | 0.5 | 0.80 | 59.7% | 68.8% | 13.2% | 18.0% |
| 50% | 0.5 | 0.95 | 52.1% | 53.3% | 30.4% | 16.2% |
| 50% | 0.7 | 0.80 | 43.9% | 19.2% | 74.9% | 6.0% |
| 50% | 0.7 | 0.95 | 33.2% | 2.2% | 97.4% | 0.4% |
| 66% | 0.2 | 0.80 | 82.1% | 83.3% | 0.0% | 16.7% |
| 66% | 0.2 | 0.95 | 78.6% | 83.7% | 0.0% | 16.3% |
| 66% | 0.5 | 0.80 | 59.7% | 25.0% | 69.4% | 5.6% |
| 66% | 0.5 | 0.95 | 52.1% | 5.6% | 93.3% | 1.0% |
| 66% | 0.7 | 0.80 | 43.9% | 7.4% | 91.4% | 1.3% |
| 66% | 0.7 | 0.95 | 33.2% | 1.2% | 98.6% | 0.2% |
| 75% | 0.2 | 0.80 | 82.1% | 71.8% | 13.4% | 14.8% |
| 75% | 0.2 | 0.95 | 78.6% | 69.7% | 16.0% | 14.2% |
| 75% | 0.5 | 0.80 | 59.7% | 8.0% | 90.1% | 1.9% |
| 75% | 0.5 | 0.95 | 52.1% | 1.7% | 97.8% | 0.5% |
| 75% | 0.7 | 0.80 | 43.9% | 1.0% | 98.7% | 0.3% |
| 75% | 0.7 | 0.95 | 33.2% | 0.0% | 100.0% | 0.0% |

## 3b: Binding constraint by collective size (all quorums pooled)

| members | pass rate | quorum-fail | deadlock | adversarial win | binding constraint |
|---|---|---|---|---|---|
| 3 | 28.5% | 66.4% | 5.1% | 0.0% | **TURNOUT/quorum** |
| 5 | 40.1% | 49.2% | 10.7% | 0.0% | **TURNOUT/quorum** |
| 9 | 39.7% | 46.9% | 13.4% | 0.0% | **TURNOUT/quorum** |
| 15 | 36.3% | 56.0% | 7.7% | 0.0% | **TURNOUT/quorum** |
| 25 | 38.9% | 53.3% | 7.8% | 0.0% | **TURNOUT/quorum** |
| 51 | 39.4% | 56.4% | 4.2% | 0.0% | **TURNOUT/quorum** |

## Derived recommendation

| quorum | best-case pass rate | worst-case pass rate |
|---|---|---|
| 50% | 83.7% | 2.2% |
| 66% | 83.7% | 1.2% |
| 75% | 71.8% | 0.0% |

- Raising quorum does not buy legitimacy here, it buys paralysis: the failure mode switches from deadlock to quorum-fail, i.e. the proposal never even gets a decision. The fix for low turnout is gasless voting and delegated (liquid) voting, not a higher democratic bar.
- Deadlock (ballots cast, threshold unmet) is at most ~18% and shrinks as apathy rises, because apathy removes the marginal voters who break ties. Where deadlock does bite, a tie-break rule is cheaper than lowering the pass threshold.
