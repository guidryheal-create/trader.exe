# Trading System TODO

This document outlines the current development priorities for the agentic trading system.

## High-Level Goals

- Complete the Polymarket trading bot with a focus on crypto markets.
- Integrate a robust workforce management system.
- Use RSS feeds as a signal source for trading decisions.
- Implement comprehensive testing and deployment procedures.
- Add and maintain clear documentation for developers and users.

## Refactor Status (Current)

- [x] Move settings module to `core/settings/config.py`.
- [x] Move UviSwap models to `core/models/uviswap.py`.
- [x] Move workforce config models/service to `core/models/workforce_config.py`.
- [x] Move asset registry to `core/models/asset_registry.py`.
- [x] Move Redis client to `core/clients/redis_client.py`.
- [x] Move observability utilities to `core/telemetry/observability.py`.
- [x] Move performance utilities to `core/utils/performance.py`.
- [x] Update imports across `core/`, `api/`, `scripts/`, and `tests/` for new module paths.
- [x] Fix stale runtime import in `core/camel_runtime/registries.py` (`asset_registry` path).
- [x] Compile validation after refactor (`python -m compileall core api scripts tests`).

## Immediate Follow-ups

- [ ] Restart Docker services to clear stale import/module cache after refactor.
- [ ] Run test suite in container (`pytest`) and fix regressions.
- [ ] Add regression test covering runtime import path for `core.camel_runtime.registries`.
- [ ] Audit `core/__init__.py` exports and keep only actively supported package-level symbols.
- [ ] Normalize type hints and model boundaries in moved modules (`workforce_config`, `performance`, `observability`).

## Documentation

- [x] Create `LICENSE` file (MIT).
- [x] Create `CONTRIBUTING.md` file.
- [x] Create `README.md` with basic information.
- [ ] Add architecture diagrams and more detailed documentation to the `README.md`.

## API & UI

- [ ] CCXT integration for CEX trading.
- [ ] Unified settings UX with explicit On/Off mode toggles.
- [ ] UI settings pages for global/base config + Polymarket config.
- [ ] Account management and persistence strategy (Postgres or alternative).
- [ ] Expand test coverage for both paper and live-trade guarded paths.
- [ ] Update `.env.example` to match current settings model and defaults.
- [ ] Add copy-trading toolkit logic (on-chain/CEX) with whale-scanner support.

# quant trading toolkit
- [ ] gather more metrics optimised for LLM to correct forecasting signal errors
- [ ] enhance base context in LLM with bearish vs borrow signal header to optimise LLMsearches

# bot cycle
- [ ] copy bot cycle
- [ ] quant cycle
- [ ] strong sentiment cycle
- [ ] strong news cycle
- [ ] strong sniping / explorer cycle
- [ ] whaler scanner cycle 
    -> add to the whale list and prune interisting trader with high ROI and good trade quality
- [ ] memory prunning cycle

# strategie routeur and wheight
- [ ] auto balance mode instead of hard coded to adapt market signals 
    -> copy bot vs quant vs forecast vs sentiment vs news vs hybrid vs sniper and etc
- [ ] auto weight and balance schema

# GRPO training, RL and optimisation
- [ ] auto enhancement + unbiassed LLM specialised on trading and toolkits

# other tools and ref
https://github.com/lazy-dinosaur/ccxt-mcp
https://github.com/darkrenaissance/whallets
https://github.com/pmaji/crypto-whale-watching-app
https://github.com/ccxt/ccxt/tree/master/examples
https://github.com/taylorwilsdon/quantconnect-mcp


