# Local agent memory integrations

These adapters expose `cognitive_memory_search` and `cognitive_memory_save`.
They use the existing HTTP API, respect its privacy/write gates, preserve state roles,
and never automatically capture conversations or provide delete tools.
Model configuration (including DeepSeek) is independent of the memory adapter.

## Prerequisite

From the repository root, start the service:

```sh
uv run --locked python -m api.app
```

Both adapters accept loopback HTTP origins only; run the agent on the same machine.
For WSL/containers, localhost is relative to that environment: run the service there too.
The current service uses user IDs as namespaces, not authentication.

## OpenClaw: supplementary tool plugin

Requires a host supporting `openclaw/plugin-sdk/plugin-entry` and `definePluginEntry`.
From the repository root:

```sh
openclaw plugins install --link ./integrations/openclaw
```

Review the local source if the host requests trust approval. Merge this snippet into
OpenClaw's existing config (do not replace your other plugins or allowlists):

```json
{
  "plugins": {
    "entries": {
      "cognitive-memory": {
        "enabled": true,
        "config": { "baseUrl": "http://127.0.0.1:8765", "userId": "demo-user" }
      }
    }
  }
}
```

If a `plugins.allow` list exists, add `cognitive-memory` to it.

```sh
openclaw plugins enable cognitive-memory
openclaw plugins inspect cognitive-memory --runtime --json
```

This is a supplementary tool plugin, so it does not replace `plugins.slots.memory`
or take over the built-in `memory_search`/`memory_get` tools. Enable the two named tools
in your agent's tool policy if needed. It is for a dedicated single-user local agent:
all callers share the configured `userId`; do not enable it for a multi-user gateway.

## Hermes: native directory memory provider

Choose the **existing active profile directory**, not the Hermes source directory.
From the repository root:

```sh
uv run python integrations/install_hermes.py --home "/absolute/path/to/active/hermes-profile" --user-id demo-user
hermes memory setup
```

Select `cognitive-memory` in the wizard, then restart Hermes. The installer copies the
provider to `<profile>/plugins/cognitive-memory/` and creates
`<profile>/cognitive-memory.json` only if absent; it does not replace existing settings
or activate the provider silently. Hermes permits only one external memory provider.
Without `user_id` configuration, the namespace is derived from the profile path.
Gateway identities receive a separate hashed suffix. Explicit writes from subagent,
cron, and other non-primary contexts are blocked. Different users sharing a single
chat/profile are outside this adapter's supported scope.

## Verify

Ask the agent to explicitly use `cognitive_memory_save` to remember a non-sensitive
fact, then use `cognitive_memory_search` to retrieve it. Inspect the configured user
space in the local workbench. A successful HTTP response may still say `DROP` or
`CANDIDATE`; this must never be reported as a confirmed current fact.
Sensitive information is submitted with the `sensitive` flag and `consent=false`;
manual consent remains in the workbench. Content-based sensitive-data classification
is not implemented by these adapters; the caller must mark sensitive inputs correctly.
Service failures are returned as tool errors; they do not become successful writes.

## Validation scope

Contract tests cover registration, HTTP search/write against a temporary real API,
privacy rejection, namespace binding, and service failures. Full OpenClaw/Hermes host
activation still requires those applications locally; passing adapter tests alone is
not evidence of live host compatibility. SDKs are evolving; inspect after host updates.

References:
- https://docs.openclaw.ai/plugins/building-plugins
- https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin/

## DeepSeek Harness native bundle

See [DeepSeek Harness adapter](deepseek-harness/README.md). It registers real Cordis
memory tools and has been tested with the official 0.2.1-rc.2 tool pipeline against
a temporary API. Install with `dsh plugin --profile web add` using the absolute
`integrations/deepseek-harness` directory. Full Web/desktop activation remains unverified.
