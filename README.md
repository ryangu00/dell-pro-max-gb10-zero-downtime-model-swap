![banner](docs/assets/banner.png)

# Zero-client-change production model swap on two Dell Pro Max with GB10

> A two-node tensor-parallel vLLM cluster on Dell Pro Max with GB10 machines, where the engine was swapped from a DeepSeek-V4-Flash Vision-Exp dual stack to a Qwen3.8-Flash-Next 1M-context dual stack with **zero changes on any of the four consumer surfaces**, by making the new engine serve the *old* model name as an extra `--served-model-name` alias alongside its two real names. All switching, rollback, and health checks go through one idempotent switch script, and its teardown path dumps the last 4000 lines of every container's `docker logs` to per-container snapshot files *before* `docker rm -f`. The 2026-09-20 cutover passed its full acceptance set in a single pass. The headline finding is negative: a boolean variable shadowing a same-named function inside the thinking-tier proxy raised `TypeError: 'bool' object is not callable`, was swallowed by `except: pass`, and the request passed through untranslated — the pure-function selftest had passed; only an acceptance probe deliberately built as a "must-fail-if-not-translated" request caught it.

> **Scope of the zero-change claim.** Aliasing covers only the *model name* a client calls. It was verified for the four consumer surfaces in this cutover, not for arbitrary clients. The author reports that each surface was checked for protocol, tool-call parsing, streaming, and fallback behaviour; the per-surface, per-check evidence is **not recorded** here, and the alias alone does not by itself prove compatibility for clients not in that set.

## Why this matters

Aliasing the outgoing model name on the new engine means the four consumer surfaces keep calling the name they always called — but the alias covers only the model name, not the rest of the protocol. Per-surface compatibility (protocol, tool-call parsing, streaming, fallback) is reported as checked during this cutover, with per-check evidence **not recorded**; the alias does not by itself generalize to clients outside that set. Rollback is one command (the previous mode's full configuration, including its own proxy, is kept in place). And the failure that *would* have shipped silently was a proxy that lied: its selftest passed, the engine answered 200, and the only thing wrong was that the proxy did nothing. The lesson is portable — no proxy or shim may ship without at least one end-to-end probe whose failure mode is the *absence of the shim itself*.

## Hardware and stack

| | |
|---|---|
| Nodes | Two Dell Pro Max with GB10 machines. Dual configurations run vLLM tensor-parallel across both nodes. (Hostnames and addresses are not published; write `<NODE_A_IP>` / `<NODE_B_IP>` where an address is needed. No per-node role or service split is part of this cookbook's published scope.) |
| New engine (2026-09-20 onward, the new-engine mode) | Launched from the switch script via a cluster recipe, with these flags/JSON |

> **Prerequisites not recorded here.** OS version, driver/kernel version, CUDA version, vLLM version, container runtime version, the inter-node interconnect, the communication backend, and the host memory/storage budget are **not recorded** in the source; the same model of hardware alone is not sufficient to reproduce a tensor-parallel=2 run. The recipe driver (`run-recipe.py`) and the recipe YAML (`...qwen3.8-flash-next-nvfp4-cluster.yaml`) are referenced by the source but their contents and a fixed revision are **not recorded**; treat the flag list below as the verbatim source excerpt, not a runnable file set.

Exact flags for the new engine:

- `--port 8899`
- `--max-model-len 1000000` — this sets the *configured* context ceiling. It does not by itself prove million-token correctness; near-ceiling input, generation headroom, KV/MTP memory, and long-context accuracy were **not recorded** in this cookbook's acceptance set.
- `-e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`
- YaRN rope overrides (JSON `--hf-overrides`): `rope_type: yarn`, `factor: 4.0`, `original_max_position_embeddings: 262144`, `rope_theta: 10000000`, `mrope_interleaved: true`, `mrope_section: [11, 11, 10]`, `partial_rotary_factor: 0.25`
- Speculative decoding (JSON `--speculative-config`): `{"method":"mtp","num_speculative_tokens":4,"max_model_len":1000000}` (MTP4 draft at 1M)
- `--no-async-scheduling` (without it, 1/30 scenarios read out to `max_tokens` — see "What did not work")
- `--tool-call-parser qwen3_coder`
- fp8 KV cache
- `--served-model-name qwen3.8-flash-next local-inference-lab/Qwen3.8-Flash-Next-NVFP4 deepseek-v4-flash-vision-exp` — the **third name is the alias of the outgoing model**, the mechanism that makes the model-name change transparent to the four consumer surfaces

Previous engine (2026-09-01 onward, the previous-engine mode):

- DeepSeek-V4-Flash Vision-Exp dual vLLM TP2 at `:8899`, 1M context, image `dspark-vllm-gx10:0.1.1`.
- A later community cluster-recipe variant ran the same model at `--max-model-len 1048320` with two served-name aliases.
- GPU-memory-utilization default `0.87` (rationale: `0.85` lost CUDA-available memory after repeated container start/stop — 1M ctx needed 10.06 GiB of KV with only 9.6 GiB free; the ceiling reached in that run was 0.877 — see "What did not work" for the bounded claim).

Thinking-tier proxy (the tier proxy, published separately as the thinking-tier-proxy cookbook):

- A thin HTTP shim rewriting `chat_template_kwargs.thinking` / top-level `reasoning_effort` per port.
- The fast-tier port = thinking low, the quality-tier port = thinking medium (under the previous engine these ports were off/on).
- Caller-supplied official sampling parameters are only `setdefault`-ed, never overwritten. (The proxy source is private; this behaviour is described, not published. The exact per-tier field mapping, the default sampling values, and the override precedence are **not recorded** — only the `setdefault`-only, no-overwrite contract above.)

Classic (pre-dual, rollback-anchor) stack:

- The classic stack is referenced only as the rollback anchor; its per-node service and port layout is **not part of this cookbook's published scope**.

Container restart policy:

- `--restart no` — nothing auto-starts on boot; operators run the switch script manually.

The switch script exposes a set of named modes (the script as read on 2026-09-20). Earlier snapshots describe a smaller set; the current list is the script as read on that date. (Mode names are private; see "How to reproduce" for the public abstraction.)

## How to reproduce

> Prerequisites not stated in the source sheet are marked explicitly. The switch script is **private**; this cookbook describes its behaviour and points at the public abstraction in the sibling repo `dell-pro-max-gb10-vllm-stack-ab` (`switch/stack-mode.sh`) for an executable equivalent. The sheet does not publish the switch script's filename, the repo/working directory names on the nodes, or the per-user proxy script locations; substitute your own equivalents. Internal decision-record identifiers are not published here; where the source cited one, the cookbook gives the public fact instead.

1. **Pre-decision.** Run the engine-form A/B and the thinking-caliber v3 full-table adjudication on our private 11-category eval bank (questions not published) to establish the new model as the winner. The decision owner chooses 1M context as the default, explicitly accepting the c1 −5 and ~60% slower long-coding costs to avoid a context-tier switch (see Results, Table C). The eval-bank scores below are **reported only** — they are not independently reproducible by readers; what a reader can reuse is the alias flag, the docker log-snapshot and removal order, and the acceptance-probe list — the engine build, recipe and switch script are not published, so timings are reported only.
2. **Invoke the switch script** with the Qwen3.8-Flash-Next 1M engine mode (see the public abstraction `switch/stack-mode.sh` in `dell-pro-max-gb10-vllm-stack-ab` for an equivalent). It first runs `detect()`; if the target state is already live, it exits immediately (idempotence). A complete target-state definition is **not recorded**; idempotence is keyed on the served model name being present, which can give a false "already live" if the proxy is absent or misconfigured — see the failure cases in "What did not work".
3. **`stop_all()`** tears down every candidate stack on both nodes, in this order: repo-native stop scripts (themselves idempotent), then kill of running tier-proxy processes via bracket-regex process matching (the pattern is written with a bracket around one character — e.g. `proxy[_]<marker>` — so the kill command's own command line does not contain the literal proxy name and cannot match its own shell), then — **before any `docker rm -f`** — for each candidate container on both nodes: rotate the previous snapshot (`<LOG_DIR>/lastlog-<container>.log` → `<LOG_DIR>/lastlog-<container>.log.prev`) and dump `docker logs --tail 4000 <container> > <LOG_DIR>/lastlog-<container>.log 2>&1` into `<LOG_DIR>/lastlog-<container>.log`; verify the file is non-empty before `docker rm -f`; only then `docker rm -f` the containers on both nodes. Then the classic-side containers and standby. (The explicit teardown commands are: `docker logs --tail 4000 <container> > <LOG_DIR>/lastlog-<container>.log 2>&1` to snapshot, and `docker rm -f <container>` to remove — always snapshot before remove.)
4. **Drop caches on both nodes:** `sync; echo 3 | tee /proc/sys/vm/drop_caches`. This requires write access to `/proc/sys/vm/drop_caches` on each Linux host (typically root) and must be run on **both** nodes; a non-root copy fails, and the script checks each node's exit status before proceeding. (Restart-order rule: the standby node before the main node, then drop caches — the script's start paths drop caches on both nodes before launching.)
5. **Start the target engine** (flags in "Hardware and stack") on the main node, backgrounded with its own launch log. The assembled `docker run` invocation is **not recorded**; the source gives the flags and JSON keys verbatim but not the assembled command.
6. **Wait loop.** Poll `http://<NODE_A_IP>:8899/v1/models` every 30 s for HTTP 200, and on every iteration grep the container's `docker logs` for fatal lines (`ValueError|AssertionError|NotImplementedError|died unexpectedly|Engine core initialization failed|OutOfMemory|QSA sequence length|Traceback|Conflict`) — abort fast on a match, a nominal 900-second budget (per-call timeouts not recorded). (This fail-fast check exists because a dead engine never opens its port and the wait would otherwise burn 25 minutes. The per-HTTP timeout, the total-deadline implementation, and the post-timeout state are **not recorded**; a single hung call could in principle exceed the stated budget.)
7. **Config proof.** Grep the container logs for the line `GPU KV cache size: <N> tokens` and print it — showing the KV pool the engine actually allocated. The expected value, a tolerance, and a comparison condition are **not recorded**; this step prints the observed size, it does not assert it matches a target.
8. **Start the tier proxy** on the main node, detached from the ssh session, then confirm the fast-tier port and the quality-tier port each answer 200 on `/v1/models`. The full `setsid nohup …` invocation (proxy command, args, dependencies, log path, bind address) is **not recorded**; an HTTP 200 on `/v1/models` confirms the port is up, not that translation is wired in — see "What did not work" for why that distinction matters.
9. **Acceptance probes** (see Results, Table A) — run the full set; cutover is recorded complete only when all pass. (The source cutover passed on 2026-09-20; the exact completion timestamp and time zone are **not recorded** in this cookbook.)
10. **Rollback = one command.** Switch to the previous mode (e.g. the DSV4F dual), whose full configuration is kept in place including its own proxy. Second-level rollback is the classic stack (classic config kept zero-deleted as standby). The fixed-version rollback configuration, image, and weights are **not recorded**; a historical round-trip drill does not prove the current version rolls back. Use the public abstraction `switch/stack-mode.sh` in `dell-pro-max-gb10-vllm-stack-ab` for an executable rollback path.

## Results

All eval-bank numbers below are from **our private 11-category eval bank (questions not published)**; category names (c1-kbqa … c10-sre-ops) are public. **One run unless stated.** What a reader can reuse: the alias flag, the docker log-snapshot and removal order, the acceptance-probe list; the engine build, recipe and switch script are not published, so timings are reported only. Private-bank scores are **reported only** and are not independently reproducible. Full tables with conditions live in `docs/results.md`.

**Table A — cutover acceptance, 2026-09-20** (single cutover event, all acceptance checks passed):

| Probe | Result |
|---|---|
| Stack validator `--probe` | 4/4 (the four probe definitions, the probe code, and the raw responses are **not recorded**; this is a reported count, not a published validator) |
| `/v1/models` served names on the dual port | 3 names (qwen3.8-flash-next, local-inference-lab/Qwen3.8-Flash-Next-NVFP4, deepseek-v4-flash-vision-exp alias) |
| the fast-tier port, DeepSeek-style request (`chat_template_kwargs` thinking=false + `reasoning_effort=high`) | the fast-tier probe returned HTTP 200 with a 343-character reasoning field; the assertion that the effort field was rewritten relies on the proxy's own log line, which is not reproduced here |
| the quality-tier port, same request | HTTP 200; reasoning 3.2K chars (reported as rewritten to the medium tier; that assertion likewise relies on the proxy's own log, not reproduced here) — per-check evidence not recorded |
| the quality-tier port, tool call with `reasoning_effort=max` | `tool_calls` parsed correctly — per-check evidence not recorded |
| Real request through the fast-tier port | HTTP 200; reasoning 38 chars — per-check evidence not recorded |
| GPU Xid errors, both nodes | 0 (log source, collection command, time window, and reboot boundaries are **not recorded**; treat as an unverified report value) |

Additionally: after an OTA (firmware/software update), loading the DSV4F dual stack took **59 s** (the source records no further condition detail; copied as-is — software/weights version, timing boundaries, and cache state **not recorded**).

**Table B — thinking-tier adjudication** (cited in the source as the basis for the port tiers):

| Measurement | Value |
|---|---|
| Three tiers, same score | 91.7 (all three) — private-bank score, **reported only**; the score scale, sample count, aggregation rule, and sampling settings are **not recorded** |
| low vs medium token cost | low saves 30% tokens — output tokens per run on the agentic-if category, relative to xhigh |
| low vs medium speed | low 25% faster — per-run wall clock, relative to xhigh |
| non-thinking tier quality gate | c7a 81.7 — did not pass the gate (81.7 was below the ≥90 gate), so the fast port uses thinking-low rather than non-thinking |

**Table C — engine-form A/B background** (1 run per arm):

| Comparison | Value |
|---|---|
| native 262K vs 1M, short text | native slightly better: c1 +5, c9 — native took 0.62x the wall clock of the 1M build (the 1M build took about 1.6x native) |
| Context ceiling | 1M YaRN factor 4 is the only >262K path observed in this cookbook's tested configurations; other configurations were not exhaustively tested |
| KV pool | native 3.10M tokens; 1M-YaRN 3.45M tokens (1M-YaRN larger than native). Same build, KV dtype, memory budget, and concurrency are **not recorded** |
| v3 full-table adjudication (on the 1M tier) | the Qwen3.8-Flash-Next 1M engine candidate/win: categories 11/11, wall-clock 3/3, performance 4/4, overall +3.8; c8 98.3 vs 81.7; c9 100 vs 82.3 (recorded exactly as in source). The per-task denominators, comparison baseline, score units, weights, and per-item results are **not recorded**; a single run per arm does not support an unqualified "win" — treat as one observed run |
| Cost of choosing 1M as default | c1 −5, long-coding ~60% slower (accepted tradeoff) |

**Table D — load times (conditions as stated in sources):**

| Stack | Time | Condition |
|---|---|---|
| The new-engine mode | ~3.5 min | weights warm (switch script) — timing start/stop, weights version, storage, and which cache layer "warm" means are **not recorded**; timing boundaries and cache state not recorded |
| The previous-engine mode (community-cluster variant) | ~3 min warm / ~12 min cold | switch script — timing boundaries and cache state not recorded |
| generic dual stacks | ~12–15 min | switch script, dual load — timing boundaries and cache state not recorded |
| classic single-seat worker | ~10 min | switch script, single-seat load — timing boundaries and cache state not recorded |
| The previous-engine mode | 59 s | after OTA (version, timing boundaries, and cache state **not recorded**) |

**Table E — prior-generation operational facts** (2026-09-01 cutover of the DSV4F dual):

| Item | Value |
|---|---|
| Cold prefill limit | Observation — ≥200K cold prefill reboots the host on that stack; root cause not recorded. 120–144K empirically safe. Reboot diagnostics, versions, concurrency, and memory conditions are **not recorded**; treat the 120–144K band as an observed safe range for this specific configuration, not a general limit |
| Concurrency | short requests only — cold large-prompt concurrency was observed at an ~8 tok/s floor (input/output length, concurrency count, per-request vs total throughput, measurement window, and sample count are **not recorded**; a single observation does not prove a floor) |
| Rollback | one command; classic configuration retained with zero deletions |
| dual↔classic round trip | drill validated at introduction |

**Source disagreements (listed as required):**

- Earlier snapshots of the switch script describe a smaller mode set than the script as read on 2026-09-20; the current list is the script as read on that date. (Mode names and the historical mode-count lists are private; use the public abstraction `switch/stack-mode.sh` in `dell-pro-max-gb10-vllm-stack-ab`.)
- The DSV4F dual alias changed which image/variant it pointed at after a 2026-09-17 A/B; the fixed-version before/after pointer, the two snapshots, and the rollback target are **not recorded** — do not treat the alias-pointer change as a verifiable provenance claim.
- Port-tier semantics changed between generations: the fast-tier port / quality-tier port were thinking-off/on under the previous engine and are thinking-low/medium under the Qwen3.8-Flash-Next 1M engine.

## What did not work

- **Silent proxy pass-through bug** (the headline catch): boolean variable shadowing the `inject()` function inside the proxy's `handle()` → `TypeError: 'bool' object is not callable` → swallowed by `except: pass` → request forwarded untranslated → `reasoning_effort=high` reached vLLM → **400**. The pure-function `--selftest` passed. Numbers: none — the bug is qualitative; what it proves is that "pure-function selftest passes ≠ call sites are correct".
- **Third community recipe (Ollie variant):** **5/5 launch attempts failed** on 2026-09-17; the mode is kept in the script but is currently unusable, pending a hybrid-draft module. The versions, launch commands, logs, and the source/install path of the hybrid-draft module are **not recorded**; treat this branch as unsupported rather than as a documented fix.
- **Missing `--no-async-scheduling` on the Qwen3.8-Flash-Next 1M engine:** **1/30 scenarios** read out to `max_tokens` (switch-script comment; recorded before the flag was made mandatory). Trigger identified, mechanism not proven here — the vLLM version, the triggering request, the stop reason, and the on/off comparison are **not recorded**; `--no-async-scheduling` is documented as required for the build this cookbook ran, not as a general claim.
- **GPU-memory-utilization 0.85 on 1M ctx:** after repeated container start/stop cycles, CUDA-available memory regressed — 1M ctx needed **10.06 GiB** KV with only **9.6 GiB** available; fixed at 0.87 (ceiling 0.877 reached in that run). This vLLM build's kernel raised the allocation failure; other builds were not tested. The 0.877 figure is the value reached on one run with one memory budget — it is not a permanent hardware ceiling; the model, version, co-resident processes, and pre/post-restart measurements are **not recorded**.
- **Non-thinking fast tier on the Qwen3.8-Flash-Next 1M engine:** c7a **81.7** failed the quality gate — reason the fast-tier port runs thinking-low instead of non-thinking. (Private-bank score, reported only.)
- **Legacy dual mode of the Qwen3.8-Flash-Next engine (the first recipe, ≤50K):** observation — inputs >50K killed the worker; root cause not recorded. The vLLM version, the error record, and the worker-kill mechanism are **not recorded**; this is documented as a build-specific limit with a pre-flight warning, not as an enforced length cap — a warning does not by itself block >50K requests.
- **Cold prefill ≥200K on the DSV4F dual:** observation — cold prefill ≥200K reboots the host on that stack; root cause not recorded (forbidden; 120–144K was the empirically safe band observed for that configuration). Reboot diagnostics, versions, concurrency, and memory conditions are **not recorded**.
- **`pkill -f "<script name>"` style kills:** also kill the ssh session whose command line contains the script name — must be written in bracket form (e.g. `proxy[_]<marker>` for a literal name `proxy_<marker>`), which the script now uses. (`pgrep -f` only finds and prints matching processes; it does not itself kill anything. The hazard is `pkill -f`, or feeding `pgrep -f` output into `kill`.)
- **Bare port thinking overflow:** on the unproxied `:8899`, default-deep thinking consumes the full `max_tokens` on inputs that trigger deep reasoning; routine calls must go through the tiered ports. The same property applies on the quality-tier port when callers send too-small `max_tokens` (medium reasoning fills them). The exact triggering inputs and the token budget at which it bites are **not recorded**; raise `max_tokens` for tasks that need longer reasoning and budget reasoning vs. output separately.

## Pitfalls

Symptom → root cause → fix; expanded with "how we found it" in `docs/pitfalls.md`.

- **400 from upstream on `reasoning_effort` despite a "working" proxy** → a boolean variable shadowed the same-named `inject()` function; the `TypeError` was eaten by `except: pass`; the request passed through untranslated → rename the variable, log/raise instead of swallowing, and assert in selftest that the handler source has no shadowing.
- **Proxy "passed" its selftest but broke in production** → pure-function tests never exercise the call site → ship one acceptance probe that *must fail if the proxy does not translate* (e.g. a DeepSeek-style request the engine would reject). A request succeeding and reasoning length changing is not, by itself, proof that translation happened — assert direct-to-engine failure, proxy success, and the forwarded field together.
- **Forensics impossible after a container dies** → `docker rm -f` destroys daemon-mode logs that exist only in `docker logs` → snapshot `docker logs --tail 4000` to a per-container file (with rotation) before any removal — this rule entered the script after a real forensics failure on 2026-09-19.
- **`pkill -f` kills your own ssh session** → the pattern matches the shell running the command → write the pattern with brackets around one character. (`pgrep -f` only finds matches; it does not kill. The hazard is `pkill -f`, or piping `pgrep -f` into `kill`.)
- **Startup wait blocks 25 min on a dead engine** → port-only polling → grep container logs each iteration for fatal signatures and fail immediately (a nominal 900-second budget; per-call timeouts not recorded).
- **1/30 scenarios read to `max_tokens`** → vLLM async-scheduling interaction on this build of the Qwen3.8-Flash-Next 1M engine (trigger identified, mechanism not proven here) → always `--no-async-scheduling` on that engine (the version, trigger, and stop reason are **not recorded**).
- **KV allocation fails after repeated start/stop** → CUDA available memory shrinks; 0.85 too tight → default 0.87 (0.877 reached on one run; this build's kernel raised the failure, other builds not tested).
- **Worker node killed** → legacy dual stack has a ≤50K context hard limit on this build (the version, error record, and kill mechanism are **not recorded**) → keep the mode flagged and prefer the YaRN-4 1M stack.
- **Host reboots during cold prefill** → observation: ≥200K cold prefill reboots the host on that stack; root cause not recorded → cap cold prompts at the 120–144K empirically safe band (observed for that configuration; diagnostics **not recorded**).
- **Derived-proxy file becomes unparseable after scripted edits** → docstring replacement hit the first `"""` instead of the second → target the closing delimiter explicitly.
- **Nothing comes up after a node reboot** → containers run `--restart no` by design → the switch script is the boot procedure (standby node first, then main node, drop caches).
- **Cutover "succeeded" but clients broke** → alias list forgotten on the new engine → `detect()` reads `/v1/models` and expects the outgoing name present *as an alias*; a missing alias should block the cutover from reporting success (the qwen name is matched first because the Qwen3.8-Flash-Next 1M engine carries the DeepSeek alias).

## Files

- `README.md` — this cookbook.
- `docs/results.md` — all result tables, complete, with measurement conditions.
- `docs/pitfalls.md` — pitfalls expanded (symptom / root cause / fix / how we found it).
- `docs/make_banner.py` — banner generator (pure PIL); output at `docs/assets/banner.png`.
- `docs/assets/banner.png` — the rendered banner, committed to the repo so the README header image resolves out of the box. Regenerate it with `docs/make_banner.py` if you change the layout.

## License

Apache-2.0.
