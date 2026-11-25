# Local correction memory seam

Decision: place a `PersonalMemory` module between speech recognition and the
writer. `VoxKeyController` passes each transcript through its correction
function before formatting. The Qt settings view uses the same module to show,
add, and delete rules. Keep the existing hotkey, recording, model, writer, and
paste sequence.

## Interface

```python
memory.correct(text: str, app: str | None = None) -> str
memory.add_correction(heard: str, intended: str, app: str | None = None) -> None
memory.delete_correction(heard: str, app: str | None = None) -> None
memory.list_corrections() -> list[dict]
```

The implementation owns input validation, exact word/phrase boundaries,
longest-match ordering, atomic local persistence, and thread safety. UI code
does not edit JSON or run its own replacement logic. Close spelling edits can
take effect automatically when edit learning is enabled. Rules are visible and removable;
saving the same heard phrase and scope updates that rule.
`app=None` means global; an app-specific rule wins over a global rule with the
same `heard` phrase. Invalid entries fail visibly.

The tray's **Personal memory** action shows recent successful dictations for
context and asks for the phrase VoxKey heard and the phrase the user intended.
The opt-in watcher reads the focused field containing VoxKey's recent paste
for up to two minutes. The last 50 successful outputs stay only on this PC,
with a clear-history action. It does not infer rules from unrelated edits.

## Safety and performance

- A rule is a literal phrase replacement, never a semantic rewrite or a model
  guess. A sound-alike edit such as `cash` -> `cache` can be learned only in
  that app; distinctive names and known terms can apply across apps.
- Apply corrections before writing so the word-preserving writer and
  vocabulary casing see the intended text. Do not feed all rules into the
  speech prompt; the earlier `cache` prompt caused `cash` to be misheard.
- Store rules and a bounded recent-output history under
  `%LOCALAPPDATA%\VoxKey`. Do not retain additional audio or send text to a
  network service. Provide delete and clear controls.
- Use the existing JSON and atomic-write pattern. No new database, daemon,
  machine-learning trainer, or dependency is needed at this scale.

## Verification boundary

Check that a saved correction changes a later transcript, deleting it restores
the original, case and punctuation remain intact, broad and conflicting edits
wait for review, persistence survives restart, and the
correction lookup adds negligible time relative to speech recognition.
