Mock harness for Agent wallet demo

Files:
- `mock_ledger.py`: in-process mock Ledger enforcing simple Mandate rules.
- `agent.py`: simple Agent implementation (select, build, submit, retry logic).
- `demo.py`: runs two demo scenarios (success and rejection).

Run locally:

```bash
python3 demo.py
```

This prints the chosen offers and the ledger responses for both success and rejection flows.

Run the FastAPI service locally:

```bash
# Activate your venv if you have one, then:
python run_service.py
# or using the project venv python explicitly:
/Users/jassingh/Documents/vs_projects/canton8_hack/.venv/bin/python run_service.py
```

Service endpoints available:
- `POST /propose` — propose an offer (returns `proposal_id`, `offer`, `needs_approval`).
- `POST /submit` — submit an offer (auto-submits if `auto=true` or within limits).
- `GET /status/{commandId}` — get stored audit/response for a command.
- `POST /approval/callback` — simulate owner approval callback.
