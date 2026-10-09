# Configure a generation provider

Copy `.env.example` to `.env` if you have no local configuration. Set the key, base URL, and model as a pair for your provider. The recorded local generation experiments used:

```dotenv
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://llmapi.paratera.com/v1
DEEPSEEK_MODEL=DeepSeek-V4-Flash
DEEPSEEK_THINKING=disabled
DEEPSEEK_TEMPERATURE=0.3
DEEPSEEK_MAX_TOKENS=4096
DEEPSEEK_CONNECT_TIMEOUT=10
DEEPSEEK_READ_TIMEOUT=120
DEEPSEEK_MAX_ATTEMPTS=3
```

The shipped defaults select a different endpoint/model pair. Verify support for the request parameters before using another provider. The compatibility variable names do not determine which service receives the request. Supply a base URL, not the full `/chat/completions` address.

Keep the key in `.env` or an environment variable. Shell variables override `.env`; `.env` is read from the project root even when launching elsewhere. Relative paths also resolve from that root.

Use the ordinary CLI with your own index to apply these environment settings. A frozen `--runtime-profile` fixes the endpoint, model, generation parameters, and attempt count from its manifest; only the external key and optional output directory remain configurable through the usual entry point.

The local [smoke check](troubleshoot.md) does not validate remote model availability. A real question sends excerpts and may be charged. A successful response proves API compatibility for that request, not scientific correctness or a fixed underlying model revision.

[All configuration fields](../reference/cli-and-configuration.md) · [Documentation home](../README.md)
