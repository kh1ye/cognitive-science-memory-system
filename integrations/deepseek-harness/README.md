# Cognitive Memory for DeepSeek Harness

Native Cordis bundle for DeepSeek Harness, exposing:

- `cognitive_memory_search`: retrieve records with their original state roles.
- `cognitive_memory_save`: explicitly save user-provided facts through the existing write/privacy gates.

No whole-transcript capture, no autonomous extraction, no destructive tools. No model
API key is needed by this plugin. It uses the memory service on the same machine.

## Compatibility

Validated with published `@deepseek-ai/dsh-tools@0.2.1-rc.2`,
`@deepseek-ai/dsh-system-prompt@0.2.1-rc.2`, and `@deepseek-ai/cordis@4.0.5`.
Node >=24.9.0. These are rapidly changing preview APIs, so the bundle pins its DSH
compatibility rather than claiming future versions work. Tests load real Cordis,
register real Tools, dispatch through the official pipeline and call a temporary
real API. Full DSH Web/desktop UI activation and model-directed calls are not yet verified.

## Install locally

1. From this repository root, start the existing memory server:

```sh
uv run --locked python -m api.app
```

2. In an already-installed **DSH 0.2.1-rc.2** environment, install this directory as a bundle.
Replace the path with the absolute directory on your machine:

```sh
dsh plugin --profile web add "/absolute/path/to/memory/integrations/deepseek-harness"
```

On Windows PowerShell, from this repository root:

```powershell
dsh plugin --profile web add (Resolve-Path ./integrations/deepseek-harness).Path
```

The package declares `dsh.bundle.patch`; the CLI installs and enables the bundle.
Use your actual profile name in place of `web` for a desktop or custom profile.
Restart Harness after installing. No global npm install or registry publication is required.

3. The default namespace is `dsh-local`. To use the same user as the workbench,
append this override to the active profile's `cordis.patch.yml` (normally under
`$DSH_HOME/profiles/web`, or `~/.dsh/profiles/web` if DSH_HOME is unset):

```yaml
- id: cognitive-memory
  config:
    baseUrl: http://127.0.0.1:8765
    userId: demo-user
```

The override targets the row inserted by this package's bundle patch. Preserve the
rest of your profile patch. Config replaces the whole row config, so include both
fields. Restart Harness after changing it. All sessions using this plugin instance
share this namespace; use only for a single-user local profile, not a multi-user server.
Loopback HTTP origins only; redirects are refused. In WSL or containers, run the
memory API inside the same environment, since localhost is relative to the agent.

4. Check that your agent preset exposes `cognitive_memory_search` and
`cognitive_memory_save`; tool restrictions in a preset can hide global tools.
Ask the agent to explicitly save a non-sensitive preference using
`cognitive_memory_save`, then retrieve it using `cognitive_memory_search`.
The workbench should show source `deepseek_harness_plugin` in the selected space.

`DROP` and `CANDIDATE` are valid service decisions, not confirmations of current
facts. Retrieved text is reference data, never instructions. Sensitive data must
be marked with `sensitive=true`; this adapter does not infer consent and does not
implement its own PII classifier. Use the workbench's manual consent flow if needed.
Failures throw into Harness's normal tool-error pipeline; requests time out after
15 seconds and respect cancellation. The plugin does not retry writes automatically.

## Test / inspect package

```sh
npm --prefix integrations/deepseek-harness ci --ignore-scripts --registry=https://registry.npmjs.org
npm --prefix integrations/deepseek-harness test
uv run --locked python -m unittest discover -s tests -p test_agent_integrations.py -v
npm pack ./integrations/deepseek-harness --dry-run
```

The Python integration suite supplies a temporary real HTTP API to the Node tests.
Without `MEMORY_TEST_URL`, the standalone Node command skips only that live-API case.
The test environment overrides the SDK's transitive Zod with 4.6.7 (fixing its
oversized-collection validation advisory); npm overrides are root-only and do not
change the dependencies of an installed Harness host. Keep that host updated through
its supported dependency management.

Official reference implementation used for the tool/bundle contract:
https://github.com/deepseek-ai/deepseek-harness (published tool-todo and dsh-base packages).
