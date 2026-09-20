# Results

All eval-bank numbers below are from **our private 11-category eval bank (questions not published)**; category names (c1-kbqa … c10-sre-ops) are public. **One run unless stated.** What a reader can reuse: the alias flag, the docker log-snapshot and removal order, the acceptance-probe list; the engine build, recipe and switch script are not published, so timings are reported only. Private-bank scores are **reported only** and are not independently reproducible.

## Table A — cutover acceptance

Conditions: single cutover event on 2026-09-20; verdict: all acceptance checks passed. (The exact completion timestamp and time zone are **not recorded** in this cookbook.)

| Probe | Result |
|---|---|
| Stack validator `--probe` | 4/4 — the four probe definitions, the probe code, the full requests, and the raw responses are **not recorded**; this is a reported count, not a published validator |
| `/v1/models` served names on the dual port | 3 names (qwen3.8-flash-next, local-inference-lab/Qwen3.8-Flash-Next-NVFP4, deepseek-v4-flash-vision-exp alias) |
| the fast-tier port, DeepSeek-style request (`chat_template_kwargs` thinking=false + `reasoning_effort=high`) | the fast-tier probe returned HTTP 200 with a 343-character reasoning field; the assertion that the effort field was rewritten relies on the proxy's own log line, which is not reproduced here |
| the quality-tier port, same request | HTTP 200; reasoning 3.2K chars (reported as rewritten to the medium tier; that assertion likewise relies on the proxy's own log, not reproduced here) — per-check evidence not recorded |
| the quality-tier port, tool call with `reasoning_effort=max` | `tool_calls` parsed correctly — per-check evidence not recorded |
| Real request through the fast-tier port | HTTP 200; reasoning 38 chars — per-check evidence not recorded |
| GPU Xid errors, both nodes | 0 — log source, collection command, time window, and reboot boundaries are **not recorded**; treat as an unverified report value |

Additionally: after an OTA (firmware/software update), loading the DSV4F dual stack took **59 s** (the source records no further condition detail; copied as-is — software/weights version, timing boundaries, and cache state **not recorded**).

## Table B — thinking-tier adjudication

Conditions: cited in the source as the basis for the port tiers.

| Measurement | Value |
|---|---|
| Three tiers, same score | 91.7 (all three) — private-bank score, **reported only**; the score scale, sample count, aggregation rule, and sampling settings are **not recorded** |
| low vs medium token cost | low saves 30% tokens — output tokens per run on the agentic-if category, relative to xhigh |
| low vs medium speed | low 25% faster — per-run wall clock, relative to xhigh |
| non-thinking tier quality gate | c7a 81.7 — did not pass the gate (81.7 was below the ≥90 gate), so the fast port uses thinking-low rather than non-thinking |

## Table C — engine-form A/B background

Conditions: 1 run per arm.

| Comparison | Value |
|---|---|
| native 262K vs 1M, short text | native slightly better: c1 +5, c9 — native took 0.62x the wall clock of the 1M build (the 1M build took about 1.6x native) |
| Context ceiling | 1M YaRN factor 4 is the only >262K path observed in this cookbook's tested configurations; other configurations were not exhaustively tested |
| KV pool | native 3.10M tokens; 1M-YaRN 3.45M tokens (1M-YaRN larger than native). Same build, KV dtype, memory budget, and concurrency are **not recorded** |
| v3 full-table adjudication (on the 1M tier) | the Qwen3.8-Flash-Next 1M engine candidate/win: categories 11/11, wall-clock 3/3, performance 4/4, overall +3.8; c8 98.3 vs 81.7; c9 100 vs 82.3 (recorded exactly as in source). The per-task denominators, comparison baseline, score units, weights, and per-item results are **not recorded**; a single run per arm does not support an unqualified "win" — treat as one observed run |
| Cost of choosing 1M as default | c1 −5, long-coding ~60% slower (accepted tradeoff) |

## Table D — load times

Conditions: as stated in sources (switch script unless noted).

| Stack | Time | Condition |
|---|---|---|
| The new-engine mode | ~3.5 min | weights warm (switch script) — timing start/stop, weights version, storage, and which cache layer "warm" means are **not recorded**; timing boundaries and cache state not recorded |
| The previous-engine mode (community-cluster variant) | ~3 min warm / ~12 min cold | switch script — timing boundaries and cache state not recorded |
| generic dual stacks | ~12–15 min | switch script, dual load — timing boundaries and cache state not recorded |
| classic single-seat worker | ~10 min | switch script, single-seat load — timing boundaries and cache state not recorded |
| The previous-engine mode | 59 s | after OTA (version, timing boundaries, and cache state **not recorded**) |

## Table E — prior-generation operational facts

Conditions: 2026-09-01 cutover of the DSV4F dual.

| Item | Value |
|---|---|
| Cold prefill limit | ≥200K forbidden (a host-reboot landmine on that stack); 120–144K empirically safe. Reboot diagnostics, versions, concurrency, and memory conditions are **not recorded**; treat the 120–144K band as an observed safe range for this specific configuration, not a general limit |
| Concurrency | short requests only — cold large-prompt concurrency was observed at an ~8 tok/s floor (input/output length, concurrency count, per-request vs total throughput, measurement window, and sample count are **not recorded**; a single observation does not prove a floor) |
| Rollback | one command; classic configuration retained with zero deletions |
| dual↔classic round trip | drill validated at introduction |

## Source disagreements

Listed as required by the source sheet.

- Earlier snapshots of the switch script describe a smaller mode set than the script as read on 2026-09-20; the current list is the script as read on that date. (Mode names and the historical mode-count lists are private; use the public abstraction `switch/stack-mode.sh` in `dell-pro-max-gb10-vllm-stack-ab`.)
- The DSV4F dual alias changed which image/variant it pointed at after a 2026-09-17 A/B; the fixed-version before/after pointer, the two snapshots, and the rollback target are **not recorded** — do not treat the alias-pointer change as a verifiable provenance claim.
- Port-tier semantics changed between generations: the fast-tier port / quality-tier port were thinking-off/on under the previous engine and are thinking-low/medium under the Qwen3.8-Flash-Next 1M engine.
