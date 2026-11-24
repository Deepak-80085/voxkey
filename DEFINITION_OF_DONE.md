# Definition of Done

Every change to VoxKey meets each line it touches before it is called done.

1. **Tests**: each new rule or behavior has a pytest test; `pytest` passes.
2. **Typing never breaks**: existing dictation tests pass, and plain dictation ("hello good morning") still types in a real app.
3. **Real-app proof**: each affected golden example (DECISIONS.md) is tried by voice on the real PC before done.
4. **Failures are visible**: missing app, folder not found, or failed launch shows the error note; never a crash or silence.
5. **Safe keys**: keystrokes are sent only after confirming the target window is in front.
6. **Speed**: dictation no slower than before; a command starts its action within 1 s of key release (measured from the log).
7. **Docs match**: README, docs/architecture.md, docs/privacy.md updated when behavior changes.
