# Pitfalls

Each pitfall is given as **symptom / root cause / fix / how we found it**. Numbers are reproduced unchanged from the source sheet with their conditions; where the source gives no number, the pitfall is qualitative.

---

## 1. 400 from upstream on `reasoning_effort` despite a "working" proxy

- **Symptom:** A DeepSeek-style request sent to the thinking-tier proxy with `reasoning_effort=high` came back **400** from vLLM, even though the proxy reported its `--selftest` as passing.
- **Root cause:** Inside the proxy's `handle()`, a boolean variable shadowed the same-named `inject()` function. When the handler called `inject(...)`, Python resolved the name to the boolean and raised `TypeError: 'bool' object is not callable`. The handler wrapped the call in `except: pass`, so the exception was swallowed and the request was forwarded **untranslated** — the caller's `reasoning_effort=high` reached vLLM and was rejected. The pure-function `--selftest` exercised `inject()` in isolation, where the shadowing did not occur, so it passed.
- **Fix:** Rename the boolean so it cannot shadow the function; log/raise instead of `except: pass`; and assert in selftest that the handler source contains no name that is both a function and a local variable (a static shadowing check on the AST).
- **How we found it:** Only an acceptance probe deliberately built as a "must-fail-if-not-translated" request — a DeepSeek-style request the engine would reject if `reasoning_effort` reached it untranslated — caught the bug. The probe observed a 400 where the tiered port should have rewritten the field and returned 200. Numbers: none — the bug is qualitative. The lesson: "pure-function selftest passes ≠ call sites are correct".

## 2. Proxy "passed" its selftest but broke in production

- **Symptom:** The proxy selftest was green, the engine answered HTTP 200 on `/v1/models`, and the only thing wrong was that the proxy did nothing to real traffic.
- **Root cause:** Pure-function tests never exercise the call site; they prove the transformation function in isolation, not that the handler wires it into the request path.
- **Fix:** Ship at least one end-to-end acceptance probe whose *failure mode is the absence of the shim itself* — e.g. a DeepSeek-style request the engine would reject if the proxy did not translate it. To prove translation (not merely that the request succeeded and reasoning length changed), assert three things together: a direct-to-engine request is rejected with the un-translated field, a proxy request with the same field succeeds, and the forwarded field actually matches the tier rewrite.
- **How we found it:** The 400 from pitfall #1 surfaced this gap directly; the selftest had passed, so the gap was invisible until an end-to-end probe was added.

## 3. Forensics impossible after a container dies

- **Symptom:** After a container was removed, there were no daemon-mode logs to inspect — the failure was gone.
- **Root cause:** `docker rm -f` destroys daemon-mode logs that exist only in `docker logs`. Once the container is gone, so is the evidence.
- **Fix:** Before any `docker rm -f`, snapshot `docker logs --tail 4000 <container> > <LOG_DIR>/lastlog-<container>.log 2>&1` to a per-container file (merging stderr, since a non-TTY container's error logs otherwise survive only in `docker logs`), with rotation (`<LOG_DIR>/lastlog-<container>.log` → `<LOG_DIR>/lastlog-<container>.log.prev`). Verify the file is non-empty before `docker rm -f`. The switch script's `stop_all()` does this on both nodes for every candidate container, then runs `docker rm -f <container>`.
- **How we found it:** A real forensics failure on 2026-09-19 — the day before cutover — where a dead container had been removed and the cause could not be reconstructed. The snapshot-before-removal rule entered the script the next day.

## 4. `pkill -f` kills your own ssh session

- **Symptom:** A `pkill -f "<script name>"` intended to stop the tier proxy also killed the ssh session running the command.
- **Root cause:** The shell's own command line contains the script name, so the pattern matches the shell running the command. (`pgrep -f` only finds and prints matching processes; it does not itself kill anything. The hazard is `pkill -f`, or piping `pgrep -f` output into `kill`.)
- **Fix:** Write the pattern with brackets around one character — e.g. `proxy[_]<marker>` for a script whose literal name is `proxy_<marker>` — so the literal script name no longer appears verbatim in the kill command's own command line. The switch script now uses this form for proxy kills.
- **How we found it:** Killing the tier proxy via `pkill -f` disconnected the operator's ssh session mid-teardown.

## 5. Startup wait blocks 25 min on a dead engine

- **Symptom:** The wait loop for the new engine to come up sat for ~25 minutes before giving up on an engine that had died during startup.
- **Root cause:** Port-only polling: a dead engine never opens its port, so the loop just waits for the full timeout.
- **Fix:** On every poll iteration, grep the container's `docker logs` for fatal signatures — `ValueError|AssertionError|NotImplementedError|died unexpectedly|Engine core initialization failed|OutOfMemory|QSA sequence length|Traceback|Conflict` — and abort immediately on a match. A nominal 900-second budget (per-call timeouts not recorded).
- **How we found it:** An earlier cutover burned 25 minutes waiting on a port that never opened.

## 6. 1/30 scenarios read to `max_tokens`

- **Symptom:** On the Qwen3.8-Flash-Next 1M engine (before `--no-async-scheduling` was mandatory), **1/30** scenarios read out to `max_tokens` instead of stopping.
- **Root cause:** Trigger identified, mechanism not proven here — a vLLM async-scheduling interaction on the Qwen3.8-Flash-Next 1M engine (this build only — the vLLM version, the triggering request, and the stop reason are **not recorded**; other builds were not tested).
- **Fix:** Always launch the Qwen3.8-Flash-Next 1M engine with `--no-async-scheduling`. The switch script records this in its comments; the flag is now mandatory.
- **How we found it:** Recorded in the switch-script comment before the flag was made mandatory.

## 7. KV allocation fails after repeated start/stop

- **Symptom:** KV allocation failed on the 1M context configuration after repeated container start/stop cycles.
- **Root cause:** CUDA-available memory regressed after repeated start/stop; `gpu-memory-utilization 0.85` was too tight — 1M ctx needed **10.06 GiB** of KV with only **9.6 GiB** free. This vLLM build's kernel raised the allocation failure; other builds were not tested.
- **Fix:** Default `gpu-memory-utilization` to `0.87` (0.877 reached on one run with one memory budget — it is not a permanent hardware ceiling; the model, version, co-resident processes, and pre/post-restart measurements are **not recorded**).
- **How we found it:** Repeated container start/stop during testing left the 1M ctx unable to allocate its KV pool at 0.85.

## 8. Worker node killed by >50K context

- **Symptom:** The worker node was killed when inputs exceeded 50K tokens.
- **Root cause:** Observation — the legacy dual mode of the Qwen3.8-Flash-Next engine (the first recipe) observed a ≤50K context limit on this build; root cause not recorded (the vLLM version, the error record, and the worker-kill mechanism are **not recorded**); inputs >50K killed the worker. A pre-flight warning does not by itself block >50K requests.
- **Mitigation:** Keep the legacy mode flagged with a pre-flight warning in the script (an actual fix that rejects >50K requests is not recorded; the warning only warns), and prefer the YaRN factor-4 1M stack for long context.
- **How we found it:** Recorded as a prior-generation operational fact attached to the legacy dual mode.

## 9. Host reboots during cold prefill

- **Symptom:** Host reboots occurred during cold prefill of large prompts on the DSV4F dual stack.
- **Root cause:** Observation — cold prefill ≥200K reboots the host on that stack; root cause not recorded. Reboot diagnostics, versions, concurrency, and memory conditions are **not recorded**; the 120–144K band is an observed safe range for that specific configuration, not a general limit.
- **Fix:** Cap cold prompts at the 120–144K empirically safe band; ≥200K cold prefill is forbidden.
- **How we found it:** Prior-generation operational fact (2026-09-01 cutover of the DSV4F dual).

## 10. Derived-proxy file becomes unparseable after scripted edits

- **Symptom:** After a scripted edit, the derived-proxy file would no longer parse.
- **Root cause:** Docstring replacement hit the first `"""` (the opening delimiter) instead of the second (the closing delimiter), corrupting the file.
- **Fix:** Target the closing delimiter explicitly rather than relying on a naive first-match replacement.
- **How we found it:** A scripted edit to the proxy source produced an unparseable file at runtime.

## 11. Nothing comes up after a node reboot

- **Symptom:** After a node reboot, no containers were running.
- **Root cause:** Containers run `--restart no` by design — nothing auto-starts on boot.
- **Fix:** The switch script is the boot procedure. Restart order: standby node first, then main node, then drop caches (`sync; echo 3 | tee /proc/sys/vm/drop_caches` — requires root on each Linux host) on both nodes before launching.
- **How we found it:** Operational rule from the 2026-09-01 DSV4F dual cutover; reinforced by the restart policy on every container.

## 12. Cutover "succeeded" but clients broke

- **Symptom:** A cutover reported success, but consumers broke because they could no longer reach the model name they expected.
- **Root cause:** The `--served-model-name` alias list was forgotten on the new engine, so the outgoing model name was no longer served.
- **Fix:** `detect()` reads `/v1/models` and expects the outgoing name present *as an alias*. The Qwen3.8-Flash-Next 1M engine carries the DeepSeek alias (`deepseek-v4-flash-vision-exp`) as its third served name; the qwen name is matched first precisely because the alias is present, and clients keep calling the name they always called. Detecting the alias is necessary but not sufficient — the engine must also be configured to serve it, and a missing alias should block the cutover from reporting success. (An older DeepSeek engine would also return the legacy name, so the check must verify the *new* model's identity, not merely that the outgoing name is present.)
- **How we found it:** The alias list is the mechanism that makes the cutover zero-client-change; omitting it is a known way to "succeed" the cutover and break consumers. (No frequency evidence ranks it against other failure modes; this is a known hazard, not "the single most likely".)
