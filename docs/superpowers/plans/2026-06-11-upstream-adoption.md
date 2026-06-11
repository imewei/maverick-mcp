# Upstream Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt 46 upstream commits — security dependency bumps, CI overhaul, dead code purge, research provider package, and docs restructure — while preserving all local resilience/SAST additions.

**Architecture:** Five sequential tasks, each independently committable. Tasks 1–3 are pure upstream adoption (no new code). Task 4 adds the research provider sub-package as a clean new module. Task 5 wires up the docs catalog and CI docs job.

**Files kept from our fork (do NOT delete):**
- `maverick_mcp/api/routers/_error_handling.py` — imported by 8 routers (our resilience work)
- `maverick_mcp/api/middleware/shutdown_gate.py` — imported by `server.py` (our resilience work)
- `docs/runbooks/asyncio-systemexit.md`, `otel-protobuf-crash.md`, `transient-loop-singletons.md`, `mcp-client-serialization.md` — our operational docs
- `docs/security/DEPENDENCY_AUDIT.md` — our SAST work

**Tech Stack:** Python 3.12, uv, FastMCP, GitHub Actions, pytest, ruff, ty

---

### Task 1: Dependency Sync

**Files:**
- Modify: `pyproject.toml`
- Auto-updated: `uv.lock`

- [ ] **Step 1: Confirm current lower bounds**

```bash
grep -E '^\s+"(fastmcp|langchain|langgraph|anthropic|openai|yfinance|cryptography|plotly|greenlet|python-multipart)' pyproject.toml
```

Expected output shows old lower bounds (fastmcp>=2.7.0, langgraph>=0.4.8, etc.).

- [ ] **Step 2: Update version constraints in pyproject.toml**

In `pyproject.toml`, under `[project] dependencies`, replace the following lines (update the lower bounds, leave package names and other flags unchanged):

| Old | New |
|---|---|
| `"fastmcp>=2.7.0"` | `"fastmcp>=3.3.1"` |
| `"python-multipart>=0.0.20"` | `"python-multipart>=0.0.27"` |
| `"langchain>=0.3.25"` | `"langchain>=1.3.1"` |
| `"langchain-anthropic>=0.3.15"` | `"langchain-anthropic>=1.4.3"` |
| `"langchain-community>=0.3.24"` | `"langchain-community>=0.4.2"` |
| `"langchain-openai>=0.3.19"` | `"langchain-openai>=1.2.2"` |
| `"langchain-mcp-adapters>=0.1.6"` | `"langchain-mcp-adapters>=0.2.2"` |
| `"langgraph>=0.4.8"` | `"langgraph>=1.2.1"` |
| `"langgraph-checkpoint-sqlite>=3.0.0"` | `"langgraph-checkpoint-sqlite>=3.1.0"` |
| `"langgraph-supervisor>=0.0.18"` | `"langgraph-supervisor>=0.0.31"` |
| `"anthropic>=0.52.2"` | `"anthropic>=0.104.1"` |
| `"openai>=1.84.0"` | `"openai>=2.38.0"` |
| `"greenlet>=3.0.0"` | `"greenlet>=3.5.1"` (both occurrences) |
| `"yfinance>=0.2.63"` | `"yfinance>=1.4.0"` |
| `"cryptography>=42.0.0"` | `"cryptography>=48.0.0"` |
| `"plotly>=5.0.0"` | `"plotly>=6.7.0"` |

- [ ] **Step 3: Sync and update lock file**

```bash
uv sync
```

Expected: resolves successfully, `uv.lock` is updated with new pinned versions.

If resolution fails: run `uv sync --upgrade-package <failing-package>` to isolate the conflict.

- [ ] **Step 4: Verify package imports**

```bash
uv run python -c "
import fastmcp, langchain, langgraph, anthropic, openai, yfinance, cryptography
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 5: Verify server startup import**

```bash
uv run python -c "from maverick_mcp.api.server import create_server; print('Server import OK')"
```

Expected: `Server import OK`

- [ ] **Step 6: Run unit tests**

```bash
COVERAGE_CORE=sysmon uv run pytest -x -q -m "not integration and not slow and not external" 2>&1 | tail -20
```

Expected: tests pass. If failures appear, note them — they likely indicate an API change in a bumped package that needs a targeted fix.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build(deps): bump dependency lower bounds to upstream — security + major version alignment

Security fixes: aiohttp, cryptography>=48.0.0, idna (via transitive).
Major bumps: fastmcp 2.7→3.3, langgraph 0.4→1.2, openai 1.84→2.38,
yfinance 0.2→1.4, anthropic 0.52→0.104."
```

---

### Task 2: CI Workflow Overhaul

**Files:**
- Create: `.github/workflows/ci.yml`
- Delete: `.github/workflows/dep-smoke.yml`
- Modify: `.github/workflows/claude-code-review.yml`
- Modify: `Makefile`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

Create `.github/workflows/ci.yml` with this exact content (we'll add the `docs` job in Task 5 once the catalog is set up):

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    name: Lint (ruff)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@94527f2e458b27549849d47d273a16bec83a01e9
        with:
          python-version: "3.12"
          enable-cache: true
      - name: Sync dependencies
        run: uv sync --extra dev --frozen
      - name: Ruff check
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .

  typecheck:
    name: Type check (ty, baseline)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@94527f2e458b27549849d47d273a16bec83a01e9
        with:
          python-version: "3.12"
          enable-cache: true
      - name: Sync dependencies
        run: uv sync --extra dev --frozen
      - name: ty check, full package (informational)
        continue-on-error: true
        run: uv run ty check maverick_mcp
      - name: ty check, strict zone (services/ + domain/)
        run: uv run ty check maverick_mcp/services maverick_mcp/domain

  test-unit:
    name: Unit tests (pytest)
    runs-on: ubuntu-latest
    env:
      MAVERICK_TEST_ENV: "true"
      TIINGO_API_KEY: "ci-dummy-key"
    steps:
      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@94527f2e458b27549849d47d273a16bec83a01e9
        with:
          python-version: "3.12"
          enable-cache: true
      - name: Sync dependencies
        run: uv sync --extra dev --frozen
      - name: Run unit tests
        run: |
          COVERAGE_CORE=sysmon uv run pytest \
            -m "not integration and not slow and not external" \
            --maxfail=5 \
            --timeout=60
```

- [ ] **Step 2: Delete dep-smoke.yml**

```bash
git rm .github/workflows/dep-smoke.yml
```

- [ ] **Step 3: Replace claude-code-review.yml with upstream version**

```bash
git show upstream/main:.github/workflows/claude-code-review.yml > .github/workflows/claude-code-review.yml
```

Verify the file starts with `name: Claude Code Review` and contains the fork-guard condition:
```bash
grep "head.repo.full_name" .github/workflows/claude-code-review.yml
```
Expected: line found (confirms fork guard is present).

- [ ] **Step 4: Update Makefile — remove 4 dead targets**

In `Makefile`, make these changes:

**Line 4 (.PHONY):** Remove `check-mcp-types check-otel-versions check-mcp-descriptions check-router-variants` from the `.PHONY` list. Add `docs-check`.

**Lines 164–187:** Delete these four target blocks entirely:
```makefile
check-mcp-types:
	@echo "Checking MCP tool list[str] parameters use coercion aliases..."
	@uv run python scripts/check_mcp_list_types.py

check-otel-versions:
	@echo "Checking OpenTelemetry package versions are aligned in uv.lock..."
	@uv run --no-sync python scripts/check_otel_versions.py

# check-mcp-descriptions is now --strict: ...
check-mcp-descriptions:
	...
	@uv run python scripts/check_mcp_descriptions.py --strict

# check-router-variants stays warning-only ...
check-router-variants:
	...
	@uv run python scripts/check_router_variants.py
```

**Line 188 (`check:` target):** Replace:
```makefile
check: lint typecheck check-mcp-types check-otel-versions check-mcp-descriptions check-router-variants
```
With:
```makefile
check: lint typecheck
```

**After the `typecheck:` block**, add:
```makefile
docs-check:
	@echo "Validating documentation catalog..."
	@uv run python tools/check_docs_catalog.py
```

**In the `help:` block**, add after the typecheck line:
```makefile
	@echo "  make docs-check   - Validate documentation catalog and links"
```

- [ ] **Step 5: Verify Makefile parses cleanly**

```bash
make --dry-run check 2>&1 | head -5
```

Expected: shows `lint` and `typecheck` commands, no "No rule to make target" errors.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/claude-code-review.yml Makefile
git commit -m "ci: replace dep-smoke with unified ci.yml; upgrade claude-code-review to v1 patterns

- New ci.yml: lint + typecheck + unit tests with pinned action SHAs
- claude-code-review.yml: fork guard, Opus 4.8 model, inline comments
- Makefile: drop 4 stale script targets, add docs-check stub"
```

---

### Task 3: Dead Code Purge

**Files deleted:**
- `maverick_mcp/api/routers/screening_ddd.py`
- `maverick_mcp/api/routers/screening_parallel.py`
- `maverick_mcp/api/routers/technical_ddd.py`
- `maverick_mcp/api/routers/data_enhanced.py`
- `maverick_mcp/api/services/` (entire directory: `__init__.py`, `base_service.py`, `market_service.py`, `portfolio_service.py`, `prompt_service.py`, `resource_service.py`)
- `scripts/check_mcp_list_types.py`
- `scripts/check_otel_versions.py`
- `scripts/check_router_variants.py`
- `scripts/check_mcp_descriptions.py`

**Files kept (actively used — do NOT touch):**
- `maverick_mcp/api/routers/_error_handling.py`
- `maverick_mcp/api/middleware/shutdown_gate.py`

- [ ] **Step 1: Confirm routers have no live importers**

```bash
grep -rn "screening_ddd\|screening_parallel\|technical_ddd\|data_enhanced" maverick_mcp/ \
  --include="*.py" | grep -v __pycache__ | \
  grep -v "maverick_mcp/api/routers/screening_ddd.py\|maverick_mcp/api/routers/screening_parallel.py\|maverick_mcp/api/routers/technical_ddd.py\|maverick_mcp/api/routers/data_enhanced.py"
```

Expected: no output. If output appears, those routers are still imported — investigate before deleting.

- [ ] **Step 2: Confirm services/ has no importers**

```bash
grep -rn "from maverick_mcp.api.services\|from \.services\|import services" \
  maverick_mcp/ --include="*.py" | grep -v __pycache__
```

Expected: no output.

- [ ] **Step 3: Delete stale router files**

```bash
git rm maverick_mcp/api/routers/screening_ddd.py \
        maverick_mcp/api/routers/screening_parallel.py \
        maverick_mcp/api/routers/technical_ddd.py \
        maverick_mcp/api/routers/data_enhanced.py
```

- [ ] **Step 4: Delete services layer**

```bash
git rm -r maverick_mcp/api/services/
```

- [ ] **Step 5: Delete stale scripts**

```bash
git rm scripts/check_mcp_list_types.py \
        scripts/check_otel_versions.py \
        scripts/check_router_variants.py \
        scripts/check_mcp_descriptions.py
```

- [ ] **Step 6: Verify server still imports cleanly**

```bash
uv run python -c "from maverick_mcp.api.server import create_server; print('OK')"
```

Expected: `OK` — if this fails, a deleted file was still imported; use the traceback to identify the remaining dependency and fix it before committing.

- [ ] **Step 7: Run unit tests**

```bash
COVERAGE_CORE=sysmon uv run pytest -x -q -m "not integration and not slow and not external" 2>&1 | tail -10
```

Expected: same pass count as after Task 1. Any new failures indicate a missed import to fix.

- [ ] **Step 8: Commit**

```bash
git commit -m "chore: remove dead router variants, services layer, and stale scripts

Deleted: screening_ddd, screening_parallel, technical_ddd, data_enhanced routers
Deleted: api/services/ layer (zero importers found)
Deleted: check_mcp_list_types, check_otel_versions, check_router_variants,
         check_mcp_descriptions scripts (replaced by ruff/ty/ci.yml)"
```

---

### Task 4: Research Provider Package

**Files created:**
- `maverick_mcp/agents/research/__init__.py`
- `maverick_mcp/agents/research/providers/__init__.py`
- `maverick_mcp/agents/research/providers/base.py`
- `maverick_mcp/agents/research/providers/exa.py`
- `maverick_mcp/agents/research/providers/tavily.py`

These providers are standalone new modules. They don't replace anything in the existing `maverick_mcp/agents/` layer — they extend it with a structured provider pattern that the research router can wire to later.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p maverick_mcp/agents/research/providers
touch maverick_mcp/agents/research/__init__.py
touch maverick_mcp/agents/research/providers/__init__.py
```

- [ ] **Step 2: Pull base.py from upstream**

```bash
git show upstream/main:maverick_mcp/agents/research/providers/base.py \
  > maverick_mcp/agents/research/providers/base.py
```

Verify:
```bash
uv run python -c "from maverick_mcp.agents.research.providers.base import WebSearchProvider; print('base OK')"
```

Expected: `base OK`

- [ ] **Step 3: Pull exa.py from upstream**

```bash
git show upstream/main:maverick_mcp/agents/research/providers/exa.py \
  > maverick_mcp/agents/research/providers/exa.py
```

Verify:
```bash
uv run python -c "from maverick_mcp.agents.research.providers.exa import ExaSearchProvider; print('exa OK')"
```

Expected: `exa OK` — if `ImportError` appears, check that `maverick_mcp.exceptions` exists (`ls maverick_mcp/exceptions.py` should show the file).

- [ ] **Step 4: Pull tavily.py from upstream**

```bash
git show upstream/main:maverick_mcp/agents/research/providers/tavily.py \
  > maverick_mcp/agents/research/providers/tavily.py
```

Verify:
```bash
uv run python -c "from maverick_mcp.agents.research.providers.tavily import TavilySearchProvider; print('tavily OK')"
```

Expected: `tavily OK`

- [ ] **Step 5: Confirm full package imports**

```bash
uv run python -c "
from maverick_mcp.agents.research.providers.base import WebSearchProvider
from maverick_mcp.agents.research.providers.exa import ExaSearchProvider
from maverick_mcp.agents.research.providers.tavily import TavilySearchProvider
print('All providers import OK')
"
```

Expected: `All providers import OK`

- [ ] **Step 6: Commit**

```bash
git add maverick_mcp/agents/research/
git commit -m "feat: adopt upstream research provider package (exa, tavily, base)

Adds maverick_mcp/agents/research/providers/ with WebSearchProvider base
class and two concrete implementations. Not yet wired to a router —
these become available for future research router integration."
```

---

### Task 5: Docs Additions + Catalog + CI Docs Job

**Files created:**
- `docs/CATALOG.md`
- `docs/features/deep-research.md`
- `docs/features/portfolio.md`
- `docs/references/llm-documentation-hygiene.md`
- `docs/runbooks/claude-desktop.md`
- `docs/runbooks/database-setup.md`
- `tools/check_docs_catalog.py`

**Files modified:**
- `docs/api/backtesting.md`
- `.github/workflows/ci.yml` (add `docs` job)

- [ ] **Step 1: Pull upstream doc files**

```bash
git show upstream/main:docs/CATALOG.md > docs/CATALOG.md
mkdir -p docs/features docs/references
git show upstream/main:docs/features/deep-research.md > docs/features/deep-research.md
git show upstream/main:docs/features/portfolio.md > docs/features/portfolio.md
git show upstream/main:docs/references/llm-documentation-hygiene.md > docs/references/llm-documentation-hygiene.md
git show upstream/main:docs/runbooks/claude-desktop.md > docs/runbooks/claude-desktop.md
git show upstream/main:docs/runbooks/database-setup.md > docs/runbooks/database-setup.md
git show upstream/main:docs/api/backtesting.md > docs/api/backtesting.md
git show upstream/main:tools/check_docs_catalog.py > tools/check_docs_catalog.py
```

- [ ] **Step 2: Run docs-check to find catalog gaps**

```bash
uv run python tools/check_docs_catalog.py 2>&1
```

The checker will report any docs that are in the repo but not in `docs/CATALOG.md`. These are our fork-specific docs that upstream doesn't know about. Note all "uncatalogued" entries.

- [ ] **Step 3: Add fork-specific docs to CATALOG.md**

Open `docs/CATALOG.md` and add entries for each file reported as uncatalogued. Our fork-specific docs to add:

```markdown
## Runbooks

- [asyncio-systemexit.md](runbooks/asyncio-systemexit.md) — Handling SystemExit in asyncio event loops
- [otel-protobuf-crash.md](runbooks/otel-protobuf-crash.md) — OpenTelemetry protobuf version conflict fix
- [transient-loop-singletons.md](runbooks/transient-loop-singletons.md) — Transient loop singleton pitfalls
- [mcp-client-serialization.md](runbooks/mcp-client-serialization.md) — MCP client list[str] serialization

## Security

- [security/DEPENDENCY_AUDIT.md](security/DEPENDENCY_AUDIT.md) — Dependency security audit results
```

Add any other files flagged by the checker.

- [ ] **Step 4: Run docs-check again — must pass cleanly**

```bash
uv run python tools/check_docs_catalog.py
echo "exit code: $?"
```

Expected: exit code 0. Iterate on CATALOG.md until this passes.

- [ ] **Step 5: Add `docs` job to ci.yml**

In `.github/workflows/ci.yml`, add after the `lint` job and before `typecheck`:

```yaml
  docs:
    name: Docs catalog
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@94527f2e458b27549849d47d273a16bec83a01e9
        with:
          python-version: "3.12"
          enable-cache: true
      - name: Check docs catalog
        run: make docs-check
```

- [ ] **Step 6: Final smoke test**

```bash
make docs-check
uv run python -c "from maverick_mcp.api.server import create_server; print('server OK')"
COVERAGE_CORE=sysmon uv run pytest -x -q -m "not integration and not slow and not external" 2>&1 | tail -5
```

All three should succeed.

- [ ] **Step 7: Commit**

```bash
git add docs/ tools/check_docs_catalog.py .github/workflows/ci.yml
git commit -m "docs: adopt upstream docs restructure + catalog enforcement

New: docs/CATALOG.md, docs/features/, docs/references/, tools/check_docs_catalog.py
Updated: docs/api/backtesting.md, docs/runbooks/{claude-desktop,database-setup}.md
CI: add docs job to ci.yml (make docs-check)"
```
