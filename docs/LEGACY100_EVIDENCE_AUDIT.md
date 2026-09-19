# Preserved 100-record evidence audit

Offline replay of the immutable saved results. No model calls, source repairs or new truth labels.
All 100 records remain: 97 completed, 3 terminal errors; 88 first successes, 9 recoveries from 12 retries.
All 2,425 valid tag outcomes are counted independently of the 498 comparable legacy booleans.
Identity and explicit source-span reviews remain pending. Type eligibility below is only a pre-identity diagnostic, not publication approval.

| Tag | Text type eligible / 100 | Present | Absent | Insufficient | Conflicting | Errors | Legacy comparable / 97 |
|---|---:|---:|---:|---:|---:|---:|---:|
| visual_pixel_art | 0 | 0 | 0 | 97 | 0 | 3 | 24 |
| visual_realistic | 0 | 0 | 0 | 97 | 0 | 3 | 38 |
| visual_stylized | 0 | 0 | 0 | 97 | 0 | 3 | 63 |
| visual_first_person | 0 | 0 | 3 | 94 | 0 | 3 | 2 |
| visual_third_person | 0 | 1 | 1 | 95 | 0 | 3 | 1 |
| visual_isometric | 0 | 0 | 0 | 97 | 0 | 3 | 0 |
| visual_side_scrolling | 0 | 0 | 0 | 97 | 0 | 3 | 3 |
| mechanic_melee_combat | 0 | 3 | 0 | 94 | 0 | 3 | 0 |
| mechanic_ranged_combat | 0 | 2 | 0 | 95 | 0 | 3 | 0 |
| mechanic_real_time_combat | 0 | 3 | 1 | 93 | 0 | 3 | 4 |
| mechanic_turn_based_combat | 0 | 1 | 1 | 95 | 0 | 3 | 1 |
| mechanic_parry | 0 | 0 | 0 | 97 | 0 | 3 | 0 |
| mechanic_dodge_roll | 0 | 0 | 0 | 97 | 0 | 3 | 1 |
| mechanic_stamina | 0 | 1 | 0 | 96 | 0 | 3 | 1 |
| mechanic_crafting | 84 | 13 | 0 | 84 | 0 | 3 | 26 |
| mechanic_inventory | 0 | 0 | 0 | 97 | 0 | 3 | 6 |
| mechanic_dialogue_choices | 0 | 0 | 0 | 97 | 0 | 3 | 2 |
| world_open_world | 84 | 14 | 0 | 83 | 0 | 3 | 72 |
| world_procedural | 84 | 8 | 0 | 89 | 0 | 3 | 19 |
| feature_multiplayer | 84 | 34 | 1 | 62 | 0 | 3 | 86 |
| engagement_co_op | 84 | 20 | 1 | 76 | 0 | 3 | 5 |
| narrative_story_driven | 84 | 45 | 0 | 52 | 0 | 3 | 76 |
| gameplay_rpg | 84 | 28 | 0 | 69 | 0 | 3 | 35 |
| gameplay_shooter | 0 | 2 | 0 | 94 | 1 | 3 | 13 |
| gameplay_platformer | 0 | 0 | 0 | 97 | 0 | 3 | 20 |

There are 85 text-bearing records; 84 include a source type permitted for the seven listed documentary tags. The remaining text-only source type does not pass those allowlists. All 18 other tags have zero type-eligible original inputs. This does not turn unobserved features into negatives.

Counts of reviewed positive and negative claims are null, because that review has not happened. Original model decisions remain visible even where the new eligibility gate would have declined to evaluate.

The 77 source-title flags are review flags, not verified mismatches. No accuracy, precision, calibration or Brier claim is possible without human-reviewed truth. The saved final-call timings and partial usage are neither full-pipeline latency nor billing.

See [machine-readable audit](../experiments/legacy100/pr_b_audit.json) for frozen evidence-type rules, all new outcome counts, missing legacy comparability, and the eight text-bearing abstention decompositions.
