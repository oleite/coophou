# Generated Houdini event fixtures

Layout:

```text
houdini-<version>/hdk-api-<version>/<platform>/<adapter>/<scenario>.jsonl
```

Every line follows `schema-v1.json`. Paths and session IDs are callback-time diagnostics, never proposed collaborative identity. Fixtures in the current tree were generated in fresh `hython` processes on Houdini 21.0.729 / Windows with `HDK_API_VERSION=21000693`.

Regenerate one scenario from the repository root:

```powershell
& "$env:HFS/bin/hython.exe" scripts/run_event_probe.py --adapter hom --scenario create_node
& "$env:HFS/bin/hython.exe" scripts/run_event_probe.py --adapter hdk --scenario create_node
```

The runner deletes only the exact output fixture before recording. Its save/load/merge/clear scenario uses an isolated temporary directory and does not open an artist working file.
