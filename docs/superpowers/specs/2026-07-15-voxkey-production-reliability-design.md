# VoxKey Production Reliability Design

## Goal

Make the current Windows dictation workflow fail predictably, remain responsive
during dependency work, and leave useful local evidence when an unexpected
failure occurs.

## Scope

This phase covers startup validation, model repair, microphone cleanup,
unhandled exception logging, and diagnostic-log isolation. It does not add
onboarding, new speech models, microphone selection, signing, updates, or
branding.

## Design

### Responsive dependency work

Startup validation and tray-triggered repair run on background threads. The
controller remains the single owner of validation state and rejects concurrent
validation or repair attempts with one lock. Worker results continue to reach
Qt through the existing thread-safe `EventBus`.

### Deterministic model repair

Normal startup reuses a valid local `small.en` model. Explicit repair forces a
fresh Hugging Face download into the VoxKey-owned model directory before
loading it, replacing non-empty corrupt assets instead of trusting file size.
Failures return `Needs repair` rather than escaping into Qt.

### Crash evidence and log isolation

`VoxKeyRuntime` installs process and worker-thread exception hooks that write
full tracebacks to the local rotating `voxkey.log`. Runtime logger instances
are owned by each runtime object rather than the global logging registry, so
unit tests using temporary runtimes cannot write into the installed user's
diagnostic log.

### Capture cleanup

Recorder start, stop, close, and abort paths always clear owned stream state.
Capture failures are delivered to the HUD, which hides the orb using the
existing terminal-event mapping. No capture failure may leave a live stream or
visible orb.

## Error Handling

- Validation and repair failures set `Needs repair` with a local reason.
- Concurrent validation requests are ignored while one validation owns the lock.
- Stream close is attempted even when stream stop fails.
- Unhandled exceptions are logged locally; VoxKey does not upload crash data.

## Verification

Automated tests cover forced repair, asynchronous repair dispatch, validation
serialization, exception logging, logger isolation, stream cleanup, and the
capture-failure HUD route. The complete unit suite must pass. A packaged
Windows smoke test then verifies responsive startup, corrupt-model repair,
repeated dictations, capture failure cleanup, quit, and restart.

## Acceptance Criteria

1. Qt remains responsive during startup validation and repair.
2. Explicit repair replaces a deliberately corrupt speech model.
3. Unhandled main-thread and worker-thread exceptions appear in local logs.
4. Tests cannot add entries to the installed user's log.
5. Capture failures close the microphone and hide the orb.
6. VoxKey quits and restarts cleanly after repeated dictations.
