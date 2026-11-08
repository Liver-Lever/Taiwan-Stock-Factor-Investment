# Project instructions

- Keep all strategy decisions explicit in `configs/*.json`.
- Never use a constituent snapshot before both its `available_date` and `effective_date`.
- A month-end close signal may only affect weights on the next trading day.
- Never present `data/demo/` results as empirical investment evidence. It is synthetic fixture data.
- Production runs must fail when the source manifest is not point-in-time compliant.
- Run `behave` and the full reproduction command before reporting a change as complete.

