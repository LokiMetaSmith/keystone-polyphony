# Test: Close mesh subprocess resources before event-loop shutdown

The full pytest suite after synchronizing LokiMetaSmith/main passes, but reports PytestUnraisableExceptionWarning from asyncio subprocess cleanup: BaseSubprocessTransport.__del__ attempts to schedule a callback after the event loop has closed.

Audit test fixtures and LiminalMesh.stop() so all sidecar subprocesses, pipe transports, and background reader tasks are awaited before their loop closes. Validate with the full suite and treat unraisable exceptions as errors. This cleanup is separate from the fork synchronization and optional decision-model implementation.
