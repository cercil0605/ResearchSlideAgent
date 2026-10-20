# Construction-paper regression

`construction-regression.slidespec.json` uses three focal pages from the
user-reviewed 2026-10-20 revision: research purpose, interval-to-block generation,
and all four excavation joints in Table II.

Source: user-supplied `2026337744 1.pdf`, “Low-Code Construction Machinery Operation
Program Generation by Demonstration for Autonomous Construction”, Ishizawa et al.
The user confirmed 2026 as the citation year. Locators are embedded in the fixture;
the original PDF and accepted 24-slide deck are not distributed here.

The fixture preserves serial/parallel waiting behavior, original three-decimal
RMSE/SD values, and the distinction between command error and excavation accuracy.
It deliberately uses `purpose_mode=general` to test these three pages in isolation.
`examples/research-quality.slidespec.json` separately tests the full research flow
with clearly labeled synthetic content.

These are deterministic generation regressions, not evidence that an LLM can
reproduce the entire accepted deck or generalize to other papers. That acceptance
exercise still needs the original paper and human review.
