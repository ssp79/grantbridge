# One traced advisor run, 2026-10-21

The first AI Grant Advisor turn of the browser run (`python -m scripts.e2e_scenario`, step 10), on a new fictional account. The question was:

> Which sample grants fit us best?

These are the server's trace log lines for that turn, copied verbatim. GrantBridge logs only each step's name, type, status, time, token counts, and estimated cost; never the prompt, the reply, or profile text. `cost_usd=-` means the step made no model call. Timestamps are the server's local time (UTC−4), so 12:46 is 16:46 UTC.

The totals match what the page showed for this answer under Technical details (step 11 of the run): 4,432 input tokens (1,181 + 3,251), 445 output tokens (58 + 387), and an estimated $0.00064 ($0.000177 + $0.000464).

```
2026-10-21 12:46:04,759 INFO grantbridge.trace: trace run=5 kind=advisor_turn tool=receive_message type=code status=ok ms=0 tokens_in=0 tokens_out=0 cost_usd=-
2026-10-21 12:46:04,759 INFO grantbridge.trace: trace run=5 kind=advisor_turn tool=advisor_model type=llm status=ok ms=2822 tokens_in=1181 tokens_out=58 cost_usd=0.000177
2026-10-21 12:46:04,759 INFO grantbridge.trace: trace run=5 kind=advisor_turn tool=get_organization_profile type=tool status=ok ms=0 tokens_in=0 tokens_out=0 cost_usd=-
2026-10-21 12:46:04,759 INFO grantbridge.trace: trace run=5 kind=advisor_turn tool=search_grants type=tool status=ok ms=1 tokens_in=0 tokens_out=0 cost_usd=-
2026-10-21 12:46:04,759 INFO grantbridge.trace: trace run=5 kind=advisor_turn tool=advisor_model type=llm status=ok ms=6532 tokens_in=3251 tokens_out=387 cost_usd=0.000464
2026-10-21 12:46:04,759 INFO grantbridge.trace: trace run=5 kind=advisor_turn tool=check_reply type=code status=ok ms=10 tokens_in=0 tokens_out=0 cost_usd=-
```
