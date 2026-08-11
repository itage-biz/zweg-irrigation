# Phased plan: `zweg_irrigation` Home Assistant integration

## Phase 0 — Repository contract and delivery baseline

- Treat `master` as the protected default branch.
- Create a Python custom-component repository with the single integration domain `zweg_irrigation`; do not add native MQTT, HTTP, Zigbee, or Z-Wave drivers. The component will orchestrate existing Home Assistant `switch`, `binary_sensor`/`input_boolean`, and `number` entities, so those protocols work through their HA integrations.
- Set the initial supported baseline to Home Assistant Core `2026.7.0+` and its supported Python runtime; test against the minimum supported release and current stable release.
- Add project metadata:
  - `custom_components/zweg_irrigation/manifest.json` with name, domain, version, documentation URL, issue tracker URL, code owner, config flow, and integration type.
  - Root `hacs.json` for an integration repository, with normal repository layout—not release-zip installation.
  - `pyproject.toml` with runtime, test, lint, type-check, and coverage configuration.
  - `.gitignore`, contributor/development guidance, and an explicit decision not to add a license until the repository owner selects one.
- Success criteria: Home Assistant and HACS validation recognize exactly one integration under `custom_components/`, as required for HACS integration repositories.

## Phase 1 — Configuration model and native HA setup UI

- Implement a config flow that creates one controller entry per irrigation system and a native options flow that manages:
  - Controller name.
  - Interval in positive calendar days, absolute local start time, non-negative transition delay.
  - Optional pump `switch`.
  - Pause-condition entity restricted to `binary_sensor` or `input_boolean`.
  - Dynamic multiplier entity restricted to `number`.
  - Ordered zone records: stable UUID, name, positive duration, enabled default, and one-or-more valve `switch` entities.
- Provide add, edit, delete, and reorder-zone flows. Reject any options submission while the controller is active; the user must stop watering first.
- Store durable configuration in the config entry. Store mutable runtime state separately in a versioned HA storage record:
  - Schedule anchor and pending schedule flag.
  - Active zone, effective zone duration, elapsed time, and remaining duration.
  - Pause reasons, fault information, and prior controller state needed after restart.
- Define validation:
  - Require at least one zone and one valve per zone.
  - Accept only finite, positive multiplier values.
  - Treat unavailable/unknown pause-condition states as “pause required.”
  - Never turn on the pump when no enabled zone can run.
- Success criteria: configuration persists across HA reloads, invalid configuration is blocked before saving, and zone order is stable and user-editable.

## Phase 2 — Watering controller, schedule, and safety state machine

- Implement one serialized controller per config entry with `idle`, `running`, `paused`, and `fault-paused` states. Maintain pause causes separately: manual, condition, restart, and output fault.
- Implement full-cycle behavior:
  - Run enabled zones strictly in configured order.
  - Turn all valves in one zone on/off together.
  - Turn the optional pump on before the first zone and off after the final zone.
  - At zone handoff, close current valves, wait the configured transition delay, then open the next zone; retain pump power throughout the handoff.
  - Read and validate the multiplier immediately before every zone; snapshot it for that zone’s effective duration.
- Implement schedule behavior:
  - Anchor the schedule to the first configured local start-time occurrence after the schedule is saved; recalculate the anchor whenever schedule settings change.
  - Schedule subsequent cycles every N local calendar days, not every fixed 24-hour interval.
  - For DST spring-forward gaps, run at the first valid local instant after the gap. For fall-back repeated times, run once at the first occurrence.
  - When a due time occurs while paused or running, coalesce all missed occurrences into one pending scheduled cycle.
  - Start the pending cycle only after the active cycle ends or the blocking pause clears; never interrupt an active cycle for a later schedule.
- Implement action semantics:
  - `start_watering`: starts a complete cycle only when globally enabled, idle, condition-clear, and multiplier-valid.
  - `stop_watering`: immediately turns all valves and pump off and clears active and pending work.
  - `pause_watering`: turns outputs off and retains progress; manual pause blocks condition-clear auto-resume.
  - `resume_watering`: retries the retained activity only when globally enabled and condition-clear.
  - `start_zone`: runs one enabled zone only; reject it while another cycle is active, globally disabled, condition-paused, or multiplier-invalid.
  - Global disable immediately performs the same safe shutdown as Stop and clears all queued work.
- Define multiplier failure handling:
  - Invalid at a scheduled-cycle start: skip the cycle and record the reason.
  - Invalid before a later zone: finish the active zone, turn pump off, mark remaining zones skipped, and return idle.
- Success criteria: deterministic unit tests cover ordering, timing, handoff, all pause causes, coalesced schedules, manual actions, disabled zones, and DST calculations.

## Phase 3 — Output control, retries, recovery, and observability

- Route all pump/valve control through HA switch actions. On an unavailable entity or failed action:
  - Retry the failing command three times, five seconds apart.
  - If recovery fails, command every configured valve and pump off, persist progress, enter `fault-paused`, and require manual Resume.
- Subscribe to pause-condition entity changes and HA lifecycle events using HA’s supported state/time event helpers.
- On Home Assistant stop:
  - Persist the active zone and remaining duration.
  - Command valves and pump off.
  - Mark the work as restart-paused.
- On Home Assistant startup:
  - Restore runtime state.
  - Resume only the unwatered remainder when the controller is enabled, no manual/fault pause exists, and the pause condition is clear.
  - Otherwise remain paused until the appropriate resume condition is met.
- Emit structured `zweg_irrigation` lifecycle events and Logbook entries for cycle/zone starts, completions, pauses, resumes, stops, skipped schedules, output failures, and recovery. Event payloads include controller ID, zone ID/name where relevant, reason, timestamps, and remaining seconds.
- Success criteria: simulated output failures prove retry timing and safety shutdown; restart tests prove no valve or pump remains on and only remaining irrigation is resumed.

## Phase 4 — Home Assistant entities and user controls

- Add a synthetic HA device per controller entry and attach:
  - Global watering-enable switch.
  - Controller status sensor (`idle`, `running`, `paused`, `fault_paused`), current-zone sensor, next-run timestamp sensor, total remaining-time sensor, watering binary sensor, and paused binary sensor.
  - Per-zone enabled switch, watering binary sensor, and remaining-time sensor.
  - Button entities for Start, Stop, Pause, Resume, and each zone’s Start action.
- Register documented custom actions:
  - `zweg_irrigation.start_watering`
  - `zweg_irrigation.stop_watering`
  - `zweg_irrigation.pause_watering`
  - `zweg_irrigation.resume_watering`
  - `zweg_irrigation.start_zone`
- Make every action target the controller’s synthetic HA device; `start_zone` additionally requires the stable configured zone ID. This supports multiple controllers without ambiguous global actions.
- Show queued zones’ multiplier-adjusted estimates, count down the active zone, and show zero for completed/idle zones.
- Provide service translations and action descriptions so controls are discoverable in the HA UI and available to Assist/voice automations.
- Success criteria: all entities update immediately on state transitions; actions are selectable in Developer Tools and usable from normal HA automations.

## Phase 5 — Test suite and quality gates

- Add isolated pytest tests with Home Assistant fixtures for:
  - Config/options flows and validation.
  - State-machine timing with controlled HA time.
  - Multi-valve zones, pump lifecycle, transitions, manual controls, and disabled states.
  - Dynamic multiplier changes and invalid-value behavior.
  - Condition/manual/fault pause precedence and unavailable sensor safety.
  - Calendar interval, DST gap/repeated-time, overlapping schedule, and pending-cycle behavior.
  - Output retries, stop behavior, global disable, restart persistence, and emitted events.
- Add lint, formatting, type checking, and minimum coverage gates. CI must fail on test failures, static-analysis failures, invalid manifest/service translations, or HACS validation failures.
- Success criteria: a clean checkout can install development dependencies and execute the complete validation command locally without manual environment setup.

## Phase 6 — README and installation documentation

- Generate a root `README.md` containing:
  - Purpose, non-goals, safety warning, and supported entity/protocol model.
  - Requirements: Home Assistant Core version, HACS optionality, existing switch entities for pump/valves, an optional boolean pause entity, and optional number multiplier entity.
  - HACS installation:
    1. Install HACS.
    2. Add `https://github.com/itage-biz/zweg-irrigation` as a custom **Integration** repository.
    3. Download `Zweg Irrigation`.
    4. Restart Home Assistant.
    5. Open **Settings → Devices & services → Add integration → Zweg Irrigation**.
  - Manual installation from a GitHub Release asset into `/config/custom_components/zweg_irrigation/`, followed by restart and integration setup.
  - Guided configuration of global settings and zones.
  - Action examples in YAML, event payload examples, dashboard suggestions, lifecycle/restart semantics, DST behavior, troubleshooting, upgrade, and backup guidance.
  - Development setup, test commands, release process, issue reporting URL, and compatibility statement.
- Document that HACS uses GitHub Releases when available and falls back to the default branch otherwise; releases are preferred for stable installations.
- Success criteria: a new HA user can install via HACS or manually, configure a two-zone controller, and invoke every documented action without source-code knowledge.

## Phase 7 — GitHub CI/CD and release workflow

- Add `.github/workflows/ci.yml`:
  - Trigger on pull requests to `master` and pushes to `master`.
  - Install the pinned development environment.
  - Run formatting check, lint, type check, unit/integration tests with coverage, manifest/translation validation, and package-layout verification.
  - Upload coverage and test artifacts on failures.
- Add `.github/workflows/hacs.yml`:
  - Trigger on pull requests and pushes to `master`.
  - Run the official HACS validation action with `category: integration`.
  - Run Home Assistant Hassfest validation; do not suppress integration, manifest, service, or translation findings.
  - Pin third-party actions to immutable commit SHAs and use Dependabot to maintain GitHub Action updates.
- Add `.github/workflows/release.yml`:
  - Trigger only when a maintainer pushes a `vX.Y.Z` tag.
  - Re-run the full quality suite.
  - Validate that the tag version exactly matches `manifest.json`.
  - Build `zweg_irrigation-vX.Y.Z.zip` containing the installable `custom_components/zweg_irrigation` directory.
  - Generate a GitHub Release from the tag, attach the ZIP, and publish generated release notes.
  - Grant `contents: write` only to this workflow; all other workflows use read-only permissions.
- Configure GitHub repository settings after the first push:
  - Require CI and HACS checks before merging to `master`.
  - Require pull requests and at least one approving review.
  - Restrict direct pushes and tag creation to maintainers.
  - Enable Dependabot for GitHub Actions and Python dependencies.
  - Add repository description, relevant topics, Issues, and release notes. These are required for eventual inclusion in HACS’s default catalog; that catalog submission remains a separate, post-release decision.
- Release procedure:
  1. Update `manifest.json` version and release notes through a reviewed PR.
  2. Merge to `master` after all required checks pass.
  3. Create and push matching `vX.Y.Z` tag.
  4. Release workflow validates, packages, and publishes the GitHub Release.
  5. HACS users receive the version as an available update.

## Explicit scope boundaries

- V1 does not implement device-level protocol adapters, physical flow sensing, sunrise/sunset scheduling, native weather calculations, or built-in notification delivery.
- User notifications are intentionally implemented through emitted HA events and Logbook entries; users select their own mobile, email, or other notification targets with HA automations.
- No database migrations are involved.
