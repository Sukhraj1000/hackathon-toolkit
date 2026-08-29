AI provider notes
=================

This project includes a small AI provider abstraction at `src/canton8_hack/ai_provider.py`.

Usage
-----
- By default `main.py` uses the `MockProvider`.
- To use the Gemini stub, set environment variables and run the demo:

```bash
export AI_PROVIDER=gemini
export GEMINI_API_KEY="your_key_here"
# optionally: export GEMINI_API_URL="https://..."
python -m canton8_hack.main
```

Alternatively you can store the Gemini API key in Google Secret Manager and point
the service at the secret name. This avoids placing the key directly in the
environment:

```bash
export AI_PROVIDER=gemini
# either a short secret id (requires GOOGLE_CLOUD_PROJECT) or full resource
# path like projects/PROJECT/secrets/SECRET_NAME
export GEMINI_SECRET_NAME="my-gemini-key"
# ensure Google application credentials are available, e.g.:
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/sa.json"
python -m canton8_hack.main
```

Notes on Secret Manager
- The project will attempt to fetch `GEMINI_SECRET_NAME` from Secret Manager
	if `GEMINI_API_KEY` is not set.
- Install the Secret Manager client to enable this: `pip install google-cloud-secret-manager`.
- If the client is not installed or credentials are missing, the provider will
	fall back to raising an error explaining how to configure the API key.

Notes
-----
- `GeminiProvider` is a thin stub that posts a JSON payload with the prompt to `GEMINI_API_URL`.
- Replace the HTTP call with your preferred Gemini client for production use.
- The `prompts/agent_prompt.txt` template is used to format requests.
