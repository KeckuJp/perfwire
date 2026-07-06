# Safety

perfwire helps you plan and audit hand-soldered perfboard wiring. Read this before you rely on
its output to build something you're going to power on.

## The audit is advisory, not a safety certification

perfwire's electrical rule check (ERC) and `fabReady` gate verify a specific, fixed set of
wiring-level and topology-level rules: open nets, shorted nets, driver contention, decoupling
placement, polarity sanity, keep-away spacing, and a few others (see the README's "What it
checks" section for the full list). **A clean audit means your board passes those specific
checks — it is not a statement that the board is safe to power, and it does not replace an
independent human inspection before you apply power for the first time.**

In particular, the audit cannot see:

- Whether your schematic itself is a sound design (perfwire audits the *board*, not the *circuit
  topology's correctness*).
- Component ratings under real load (beyond the optional, opt-in resistor-power and
  decoupling-value checks).
- Physical build quality — a cold solder joint, a nicked wire, a part installed backwards in a
  way the model didn't know to check.
- Anything about a component or subsystem perfwire has no model for.

**Always visually inspect a real board and, where appropriate, verify continuity with a meter
before applying power** — perfwire's own guided-soldering mode and virtual continuity tester
exist specifically to support that step, not to replace it.

## Hazards perfwire will not help you avoid — you are responsible for these

- **Mains / line voltage.** Do not build mains-voltage (AC line) wiring on a hand-soldered
  perfboard. If your project needs to switch mains power, use a listed, enclosed, pre-built relay
  or SSR module and keep only the low-voltage control side on the perfboard. Note that an SSR can
  pass leakage current even when commanded off — a load is not guaranteed fully de-energized just
  because the control signal is low. Disconnect the actual power source (unplug it / open the
  breaker) before wiring or handling a mains-adjacent board, not just the control signal.
- **Li-ion / LiPo charging and battery circuits.** Never charge a lithium cell from a bare
  resistor or an unmanaged supply — use a proper charge-management IC, and get battery polarity
  and protection circuitry right. A charging fault here is not a "warning light" failure mode.
- **Anything perfwire's audit doesn't model** (thermal design, high current traces, RF safety,
  isolation requirements, and so on). A clean `fabReady` result says nothing about these.

## Reporting a safety-relevant gap in the audit itself

If you believe the ERC is *missing* a check that would have caught a real hazard, or is *wrong*
about one it does perform, please file an
[ERC dispute](../../issues/new?template=2_erc_dispute.yml) — see `CONTRIBUTING.md`. This is a
different thing from a general security vulnerability report; perfwire is a local, offline,
no-network tool with no accounts or infrastructure to compromise, so there is no separate
security-disclosure process beyond the normal issue tracker.

## In short

Treat every perfwire audit result the way you'd treat a very thorough, very literal-minded
checklist: valuable, worth trusting for exactly what it checks, and no substitute for your own
judgment and a final human look at the real board before power goes anywhere near it.
