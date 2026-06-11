# MCP Client Argument Serialization

**Audience:** developers adding or debugging FastMCP tools in `maverick_mcp/api/routers/`.
**TL;DR:** Never declare `list[str]` on a `@mcp.tool()` function. Use `StrList` / `OptionalStrList` from `maverick_mcp.utils.mcp_types`.

## Why

FastMCP builds a Pydantic v2 `TypeAdapter` directly from each tool function's signature. Pydantic strict mode rejects type coercion by default. Some MCP clients do **not** send list arguments as JSON arrays — they JSON-stringify the array first and send a string. Claude Desktop via `mcp-remote` is the best-documented offender; some IDE integrations exhibit the same behavior.

**Failure shape:**

```
ValidationError: 1 validation error for call[<tool_name>]
<param>
  Input should be a valid list [type=list_type, input_value='["ANET","MRVL"]', input_type=str]
```

The giveaway is `input_type=str` with a value whose text starts with `[` — the client stringified the list.

## Fix

Use the shared coercion aliases:

```python
from maverick_mcp.utils.mcp_types import StrList, OptionalStrList

@mcp.tool()
def my_tool(
    symbols: StrList,                 # required list
    tags: OptionalStrList = None,     # optional list
):
    ...
```

Both aliases apply a `BeforeValidator` that accepts:

| Input | Result |
|---|---|
| `["A","B"]` (native list) | `["A", "B"]` (unchanged) |
| `'["A","B"]'` (JSON-encoded string) | `["A", "B"]` (parsed) |
| `"AAPL"` (bare scalar) | `["AAPL"]` (wrapped) |
| `None` | `None` (for `OptionalStrList` only) |

The JSON schema the client sees still advertises `array`, so well-behaved clients are unaffected — the coercion only runs when input arrives as a `str`.

## Enforcement

- **Contract tests**: `tests/test_mcp_list_coercion.py` pins the behavior of the aliases across all 6 known input shapes. Any regression in the `BeforeValidator` breaks CI.

Note: `scripts/check_mcp_list_types.py` was removed during the June 2026 upstream adoption. The contract test suite is now the sole automated enforcement gate.

## Adding New Coerced Types

If a new parameter needs the same tolerance for a different element type (`list[int]`, `list[float]`, etc.), extend `maverick_mcp/utils/mcp_types.py`:

```python
IntList = Annotated[list[int], BeforeValidator(_coerce_json_list)]
OptionalIntList = Annotated[list[int] | None, BeforeValidator(_coerce_json_list)]
```

The `_coerce_json_list` validator is element-type-agnostic — Pydantic's downstream validation handles per-element coercion (`"1"` → `1`). Add parametrized tests to `tests/test_mcp_list_coercion.py` for the new alias.

## Exempt Code

These router types do not go through FastMCP's signature-based validation and are not affected by this constraint:

- **`performance.py`** — FastAPI router with `Field`-annotated body models.
- **Any `dataclass` field** — not a function parameter.

Note: `screening_parallel.py` was removed during the June 2026 upstream adoption.

## History

- **2026-04-14** — `get_upcoming_catalysts` in `watchlist.py` failed with `list_type` error when Claude Desktop stringified `["ANET","MRVL"]`. Investigation revealed 10 other latent call sites and one pre-existing manual fix in `compare_strategies` (`backtesting.py`). Unified into the shared aliases. This runbook was added to prevent recurrence.
- **2026-06-11** — `check_mcp_list_types.py` and `screening_parallel.py` removed as part of upstream adoption cleanup.
