# Testing, and the numbers to show investors

There are three kinds of test, from cheapest to most realistic.

## 1. Automated tests (no key, no network)

```bash
cd agent && uv run pytest
cd backend && npm test
TEST_DATABASE_URL=postgres://awaz:awaz@localhost:5432/awaz_test npm run test:e2e
```

`agent/tests/test_conversation.py` drives whole calls through the real
`flow.yaml` and tools: a full order, a WhatsApp caller, an edit after hearing
the total, unknown and ambiguous dishes, a handover to staff, and a failed
save. The LLM's choices are simulated, so these test the flow and the rules,
not Gemini.

## 2. Scripted text tests against Gemini (no microphone)

These type Dari lines at the real agent and check which tools Gemini calls.
They catch prompt problems quickly and cost a fraction of a cent each.

```bash
cd agent
uv run bot.py -t eval          # terminal 1
uv run --with "pipecat-ai[cli]==1.12.0" pipecat eval run evals/order_in_dari.yaml -v   # terminal 2
```

Add a scenario to `evals/order_in_dari.yaml` for every mistake you see in a
real call, so it never comes back.

## 3. The 30-call Dari test (the one that matters)

Text tests skip the hardest part: hearing Herati Dari over a phone line. Before
showing investors, make 30 real calls on the deployed demo:

- 10 simple orders in Dari,
- 10 orders mixing Dari and English ("یک mantu و two coke"),
- 10 hard ones: background noise, a change of mind, a landmark address,
  a dish that is not on the menu.

Use at least three different speakers, and some calls over WhatsApp from a
mobile network. Then open the dashboard: every call is logged with its
transcript, outcome, duration and estimated cost.

For each call, write down whether the saved order matched what the caller
wanted. Where it went wrong, read the transcript: a mishearing points at
speech recognition (add the word to the item's `aliases`), a wrong action
points at `flow.yaml`.

## The investor numbers

| Number | Where it comes from | Aim for |
| --- | --- | --- |
| Order accuracy | Your 30-call notes: orders saved exactly right | 80% or more |
| Finished without a human | Dashboard: "تکمیل بدون کارمند" | 70% or more |
| Response time | Seconds from the caller stopping to the agent speaking; time it on a few calls | under 2 seconds |
| Cost per call | Dashboard: "هزینه تخمینی هر تماس" | about $0.03 |
| Restaurant interest | Signed letters of intent | 3 or more |

The cost figure is an estimate from list prices (set in `.env`); compare it
with your Google Cloud bill after the 30 calls.
