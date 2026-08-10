# General feedback for `build-software-project`

These observations came from Cretona but are intentionally written as reusable
delivery rules. They are proposals for improving the skill, not project
requirements and not evidence that the skill itself was edited.

## Proposed additions

1. **Protect dual baselines before migration.** When local and remote contain
   different valid implementations, create named recovery refs and verify each
   baseline before rebasing or replacing a framework.
2. **Treat a replaced implementation as an executable oracle.** During a
   framework migration, preserve its passing tests and behavioral contracts
   until the replacement has parity evidence. Do not equate “old stack” with
   “safe to delete.”
3. **Reconcile environment contracts before feature code.** Repository root,
   source ownership, ports, base URLs, debug/release network policy, auth mode,
   provider choice, and secret locations should be a pre-implementation gate.
4. **Make synthetic/live provenance a first-class invariant.** Fake providers,
   deterministic LLM fallbacks, sample media, and mocked authentication must be
   labelled in API responses, UI evidence, and handover documents.
5. **Use an evidence ladder.** Require appropriate proof at contract/unit,
   build/static analysis, process/socket, and real client/device levels. A
   passing API test alone does not prove Android networking or media playback.
6. **Validate durable tool installation.** A tool is not sustainably installed
   until a fresh shell can resolve it, its writable state path works inside the
   actual agent sandbox, its version is recorded, and a repository preflight
   can diagnose missing optional versus required dependencies.
7. **Assert the target app before capturing UI evidence.** Device automation
   should verify the foreground package/window before trusting text, tap, or
   screenshot assertions.
8. **Separate system setup from repository history.** User-machine changes such
   as PATH, CLI installation, or tool config belong in setup evidence; only
   repository scripts/docs should be committed with the project.
9. **Pull immediately before publishing.** A successful initial pull is not
   enough on a two-developer repo. Commit and verify locally, then pull/rebase
   again directly before push and rerun any gate affected by conflict repair.

## What should remain project-specific

Do not generalize Cretona's FastAPI requirement, port 8000, Android emulator
address, SQLite exception, provider candidates, hardware thresholds, or team
owner names into the global skill. The reusable part is the decision/evidence
shape, not these values.
