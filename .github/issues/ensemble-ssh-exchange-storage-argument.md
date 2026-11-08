# Bug: Ensemble SSH exchange still passes removed LiminalMesh db_path argument

`scripts/exchange_ssh_keys.py` constructs `LiminalMesh` with
`db_path="ssh_exchange.db"`, but the current constructor accepts a
`storage_provider` instead. The default setup-ensemble path invokes this script.
Inspection during issue #95 identified the incompatible call; the issue #95
setup used the existing `SKIP_SSH_EXCHANGE=1` option and did not change SSH
permissions or repair this unrelated setup path.

Update the helper to construct the appropriate SQLiteStorageProvider, verify
cleanup, and test the default setup path without authorizing arbitrary peers.
Keep the repair separate from the durable collaboration protocol.
