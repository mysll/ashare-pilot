# Concept Sector (概念板块) API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `fetch_concept.py` script to the `stock-analysis` skill that fetches concept sector (概念板块) lists and constituent stocks from East Money.

**Architecture:** Two new methods on `EastMoneyDataSource` (`fetch_concept_list`, `fetch_concept_stocks`) wrap the existing East Money `push2.clist/get` API. A new `fetch_concept.py` script provides CLI access with two modes: list all concepts (default) and get stocks in a concept (`--code` or `--name`).

**Tech Stack:** Python 3, `requests` library, East Money `push2.eastmoney.com` JSONP API.

**Spec:** `docs/superpowers/specs/2026-06-16-concept-sector-api-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `scripts/datasources/eastmoney.py` | Modify | Add `fetch_concept_list()` and `fetch_concept_stocks()` methods |
| `scripts/fetch_concept.py` | Create | New CLI script — main user-facing interface |
| `SKILL.md` | Modify | Add "Concept Sectors (概念板块)" section + update Scripts table |
| `AGENTS.md` | Modify | Add command examples |

**Note on testing:** This skill does not use automated tests. Verification is done by running the script and checking output. The plan uses "Manual verification" steps instead of pytest.

**Note on git:** The working directory is not a git repository, so commit steps are omitted. Each task ends with manual verification of expected output.

---

## Task 1: Add data source methods to EastMoneyDataSource

**Files:**
- Modify: `scripts/datasources/eastmoney.py:485` (append after `fetch_stock_money_flow`)

- [ ] **Step 1: Add `fetch_concept_list` method**

Append the following method to `EastMoneyDataSource` class in `scripts/datasources/eastmoney.py`, after the existing `fetch_stock_money_flow` method:

```python
    def fetch_concept_list(self, page_size: int = 100) -> list:
        """Fetch all concept sectors (概念板块) from East Money.

        East Money's API caps responses at 100 items per page, so this method
        paginates automatically to fetch the complete list (~500+ concepts).

        Args:
            page_size: Number of concepts per page (default 100, max ~100)

        Returns:
            List of dicts with keys: code, name, source
            Example: [{"code": "BK0486", "name": "元宇宙", "source": "eastmoney"}, ...]
        """
        fs = "m:90+t:3"
        ut = "fa5fd1943c747385f9554f5b7d918a9e"
        fields = "f12,f14"
        headers = self._get_push2_headers()

        results = []
        page = 1
        # Cap page_size to 100 (East Money API hard limit)
        page_size = min(page_size, 100)
        while True:
            url = f"{EASTMONEY_LIST_URL}?pn={page}&pz={page_size}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"
            try:
                self._wait_for_rate_limit()
                self._check_rate_limit()
                resp = requests.get(url, headers=headers, timeout=30)
                data = resp.json()
                self._request_count += 1
            except Exception:
                break

            if not data or data.get("rc") != 0:
                break

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break

            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if not code or not name:
                    continue
                results.append(
                    {
                        "code": code,
                        "name": name,
                        "source": "eastmoney",
                    }
                )

            if len(diff) < page_size:
                break
            page += 1
            time.sleep(random.uniform(0.5, 1.5))
        return results
```

- [ ] **Step 2: Add `fetch_concept_stocks` method**

Append the following method to `EastMoneyDataSource` class, directly after `fetch_concept_list`:

```python
    def fetch_concept_stocks(self, concept_code: str) -> list:
        """Fetch stocks in a specific concept sector.

        East Money's API caps responses at 100 items per page, so this method
        paginates automatically to fetch the complete stock list for a concept.

        Args:
            concept_code: East Money concept code (e.g., "BK0486")

        Returns:
            List of dicts with keys: code, name, source
            Example: [{"code": "sh600519", "name": "贵州茅台", "source": "eastmoney"}, ...]
        """
        fs = f"b:{concept_code}+f:!2"
        ut = "fa5fd1943c747385f9554f5b7d918a9e"
        fields = "f12,f14"
        headers = self._get_push2_headers()

        results = []
        page = 1
        page_size = 100
        while True:
            url = f"{EASTMONEY_LIST_URL}?pn={page}&pz={page_size}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"
            try:
                self._wait_for_rate_limit()
                self._check_rate_limit()
                resp = requests.get(url, headers=headers, timeout=30)
                data = resp.json()
                self._request_count += 1
            except Exception:
                break

            if not data or data.get("rc") != 0:
                break

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break

            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if not code or not name:
                    continue
                # Add market prefix based on code
                if code.startswith("6"):
                    full_code = f"sh{code}"
                elif code.startswith("0") or code.startswith("3"):
                    full_code = f"sz{code}"
                elif code.startswith("8") or code.startswith("4"):
                    full_code = f"bj{code}"
                else:
                    full_code = code
                results.append(
                    {
                        "code": full_code,
                        "name": name,
                        "source": "eastmoney",
                    }
                )

            if len(diff) < page_size:
                break
            page += 1
            time.sleep(random.uniform(0.5, 1.5))
        return results
```

- [ ] **Step 3: Manual verification**

Run the following to confirm methods work. Open a Python REPL from the project root:

```bash
python -c "
import sys
sys.path.insert(0, r'.agents/skills/stock-analysis/scripts')
from datasources import EastMoneyDataSource
ds = EastMoneyDataSource()
concepts = ds.fetch_concept_list()
print(f'Fetched {len(concepts)} concepts')
print('First 3:', concepts[:3])
stocks = ds.fetch_concept_stocks('BK0486')
print(f'Fetched {len(stocks)} stocks in BK0486')
print('First 3:', stocks[:3])
"
```

**Expected output:**
- `Fetched 500+ concepts` (actual count varies, should be 400+)
- First 3 concepts have `code` like `BK0xxx` and Chinese `name`
- `Fetched N stocks in BK0486` where N > 0
- Stock codes have `sh`/`sz`/`bj` prefix

If output shows empty lists, check the East Money API response and verify `fs` parameter formatting.

---

## Task 2: Create `fetch_concept.py` script

**Files:**
- Create: `scripts/fetch_concept.py`

- [ ] **Step 1: Create the script with argument parsing and helpers**

Create `scripts/fetch_concept.py` with the following content:

```python
#!/usr/bin/env python3
"""Fetch concept sector (概念板块) data from East Money.

Lists all concept sectors or fetches stocks in a specific concept.

Usage:
    # List all concept sectors
    python fetch_concept.py
    python fetch_concept.py --json
    python fetch_concept.py --csv -o concepts.csv
    python fetch_concept.py --search "新"
    python fetch_concept.py --top 20

    # Get stocks in a specific concept
    python fetch_concept.py --code BK0486
    python fetch_concept.py --name "元宇宙"
    python fetch_concept.py --code BK0486 --json
"""

import argparse
import csv
import io
import json
import sys

from datasources import EastMoneyDataSource


_eastmoney = EastMoneyDataSource()


def fetch_concept_list() -> list:
    """Fetch all concept sectors."""
    return _eastmoney.fetch_concept_list()


def fetch_concept_stocks(concept_code: str) -> list:
    """Fetch stocks in a specific concept."""
    return _eastmoney.fetch_concept_stocks(concept_code)


def find_concept_by_name(name: str) -> str | None:
    """Find concept code by Chinese name. Returns code (e.g., BK0486) or None."""
    concepts = fetch_concept_list()
    for c in concepts:
        if c.get("name") == name:
            return c.get("code")
    return None


def print_concept_table(results: list) -> None:
    """Print concept list in table format."""
    if not results:
        print("No data.")
        return
    print(f"\n{'Code':<10} {'Name':<20}")
    print("-" * 32)
    for r in results:
        code = r.get("code", "")
        name = r.get("name", "")
        print(f"{code:<10} {name:<20}")
    print("-" * 32)
    print(f"{'TOTAL':<10} {len(results)} concepts")


def print_stock_table(results: list) -> None:
    """Print stock list in table format."""
    if not results:
        print("No data.")
        return
    print(f"\n{'Code':<12} {'Name':<20}")
    print("-" * 34)
    for r in results:
        code = r.get("code", "")
        name = r.get("name", "")
        print(f"{code:<12} {name:<20}")
    print("-" * 34)
    print(f"{'TOTAL':<12} {len(results)} stocks")


def to_csv_output(results: list) -> str:
    """Convert results to CSV format."""
    output = io.StringIO(newline="")
    fieldnames = ["code", "name", "source"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = argparse.ArgumentParser(
        description="Fetch concept sector (概念板块) data from East Money"
    )
    parser.add_argument(
        "--code",
        metavar="BK_CODE",
        help="Fetch stocks in a specific concept by East Money code (e.g., BK0486)",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        help="Fetch stocks in a specific concept by Chinese name (e.g., 元宇宙)",
    )
    parser.add_argument(
        "--search",
        metavar="KEYWORD",
        help="Filter concept list by name substring (default mode only)",
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Limit number of concepts in list mode",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV format")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")

    args = parser.parse_args()

    # Validate argument combinations
    if args.code and args.name:
        print("Error: --code and --name are mutually exclusive.", file=sys.stderr)
        sys.exit(1)
    if args.search and args.name:
        print("Error: --search and --name are mutually exclusive.", file=sys.stderr)
        sys.exit(1)
    if args.search and args.code:
        print("Error: --search only works in list mode (without --code/--name).", file=sys.stderr)
        sys.exit(1)
    if args.top and (args.code or args.name):
        print("Error: --top only works in list mode.", file=sys.stderr)
        sys.exit(1)

    # Determine mode
    if args.code:
        # Get stocks by code
        results = fetch_concept_stocks(args.code)
        if not results:
            print(f"No stocks found for concept: {args.code}")
            sys.exit(1)
    elif args.name:
        # Get stocks by name (lookup code first)
        code = find_concept_by_name(args.name)
        if not code:
            print(f"Concept not found: {args.name}")
            sys.exit(1)
        results = fetch_concept_stocks(code)
        if not results:
            print(f"No stocks found for concept: {args.name} ({code})")
            sys.exit(1)
    else:
        # List mode (default)
        results = fetch_concept_list()
        if not results:
            print("No data fetched. API may be rate-limited.")
            sys.exit(1)

        # Apply --search filter
        if args.search:
            keyword = args.search
            results = [r for r in results if keyword in r.get("name", "")]

        # Apply --top limit
        if args.top:
            results = results[: args.top]

    # Format output
    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        # Table output
        if args.code or args.name:
            print_stock_table(results)
            output_str = ""  # Already printed
        else:
            print_concept_table(results)
            output_str = ""  # Already printed

    # Save or print
    if output_str:
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(output_str)
            print(f"Saved to {args.output}")
        else:
            print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual verification — list mode**

Run:
```bash
cd .agents/skills/stock-analysis/scripts
python fetch_concept.py
```

**Expected output:** A table with ~500+ concept rows showing `Code` (e.g., `BK0001`) and `Name` (Chinese name). Last line shows `TOTAL  N concepts`.

- [ ] **Step 3: Manual verification — JSON output**

Run:
```bash
python fetch_concept.py --json --top 5
```

**Expected output:** A JSON array with 5 concept objects, each having `code`, `name`, `source`.

- [ ] **Step 4: Manual verification — search filter**

Run:
```bash
python fetch_concept.py --search "新" --top 5
```

**Expected output:** Concepts whose name contains "新" (e.g., 新能源, 芯片).

- [ ] **Step 5: Manual verification — fetch by code**

Run:
```bash
python fetch_concept.py --code BK0486
```

**Expected output:** A stock list with `sh`/`sz`/`bj` prefixed codes. If BK0486 doesn't exist or has no stocks, try another code from the list output above (e.g., `--code BK0001`).

- [ ] **Step 6: Manual verification — fetch by name**

Run:
```bash
python fetch_concept.py --name "元宇宙"
```

**Expected output:** Same stocks as the code lookup (assuming 元宇宙 exists in the list). If not, try a name visible in your list output.

- [ ] **Step 7: Manual verification — CSV output to file**

Run:
```bash
python fetch_concept.py --csv --top 10 -o /tmp/concepts.csv
cat /tmp/concepts.csv
```

**Expected output:** A CSV file with headers `code,name,source` and 10 data rows.

- [ ] **Step 8: Manual verification — error handling**

Run:
```bash
python fetch_concept.py --code BK99999
```

**Expected output:** `No stocks found for concept: BK99999` and exit code 1.

Run:
```bash
python fetch_concept.py --name "不存在的概念"
```

**Expected output:** `Concept not found: 不存在的概念` and exit code 1.

Run:
```bash
python fetch_concept.py --code BK0001 --name "test"
```

**Expected output:** `Error: --code and --name are mutually exclusive.` and exit code 1.

---

## Task 3: Update SKILL.md

**Files:**
- Modify: `SKILL.md` (add new section + update Scripts table)

- [ ] **Step 1: Add "Concept Sectors (概念板块)" section**

In `SKILL.md`, find the line `### Money Flow (资金流向)` (around line 130) and insert the following section **before** it (after the "Technical Indicators" section ends):

```markdown
### Concept Sectors (概念板块)

```bash
# List all concept sectors (~500+)
python scripts/fetch_concept.py
python scripts/fetch_concept.py --json
python scripts/fetch_concept.py --csv -o concepts.csv
python scripts/fetch_concept.py --search "新"        # Filter by name substring
python scripts/fetch_concept.py --top 20            # Top 20 concepts

# Get stocks in a specific concept
python scripts/fetch_concept.py --code BK0486        # By East Money code
python scripts/fetch_concept.py --name "元宇宙"        # By Chinese name
python scripts/fetch_concept.py --code BK0486 --json
```

Returns concept data with: `code` (e.g., BK0486), `name` (e.g., 元宇宙), `source` (eastmoney).
Stock codes in a concept are returned with `sh`/`sz`/`bj` market prefix.

```
**Note:** The opening line of the new section should be `### Concept Sectors (概念板块)` (Markdown level 3 heading). Make sure the triple-backtick code block is properly closed before the section that follows.

- [ ] **Step 2: Update the Scripts table**

In `SKILL.md`, find the Scripts table (around line 165-173). It currently has 6 rows. Add a 7th row at the end of the table:

```markdown
| `fetch_concept.py`    | Concept sectors (概念板块) & stocks   | A stocks         |
```

The full updated table should look like:

```markdown
| Script               | Purpose                          | Markets          |
| -------------------- | -------------------------------- | ---------------- |
| `fetch_stock.py`     | Real-time quotes & intraday K-line | All (intraday: A only) |
| `fetch_all_astocks.py` | Bulk real-time data (~5500 stocks) | A stocks      |
| `fetch_history.py`   | Historical daily K-line (前复权) | A stocks (sh/sz) |
| `fetch_indicators.py`| Technical indicators analysis    | A stocks (sh/sz) |
| `fetch_special.py`   | 龙虎榜 & 融资融券                | A stocks         |
| `fetch_money_flow.py`| Money flow (行业/个股资金流向) | All industries/stocks |
| `fetch_concept.py`   | Concept sectors (概念板块) & stocks | A stocks       |
```

- [ ] **Step 3: Add output fields description**

In `SKILL.md`, find the "Output Fields" section (around line 175-194). After the "Stock Money Flow" entry, add:

```markdown
**Concept Sectors**: `code` (BK0xxx), `name` (Chinese concept name), `source` (eastmoney)

**Concept Stocks**: `code` (sh/sz/bj + 6 digits), `name` (Chinese stock name), `source` (eastmoney)
```

- [ ] **Step 4: Update Notes section**

In `SKILL.md`, find the "Notes" section (around line 207-214). The first bullet list includes data sources. Find the line that mentions real-time sources and add a new line for concepts:

Current text:
```
- Real-time: Sina Finance (A/US/futures), Tencent Finance (HK)
- Intraday K-line: Sina Finance (A stocks only)
- Bulk A Stocks: Eastmoney API (default, has volume_ratio), Sina Market Center API (fallback, ~5500 stocks)
- Historical: Sohu Finance (前复权 daily K-line, A stocks only)
- Dragon & Tiger / Margin / Money Flow: East Money Datacenter API
- Stock Money Flow: East Money push2 API (requires cookie, see `.cookie` file)
```

Updated text (add new line after the Stock Money Flow line):
```
- Real-time: Sina Finance (A/US/futures), Tencent Finance (HK)
- Intraday K-line: Sina Finance (A stocks only)
- Bulk A Stocks: Eastmoney API (default, has volume_ratio), Sina Market Center API (fallback, ~5500 stocks)
- Historical: Sohu Finance (前复权 daily K-line, A stocks only)
- Dragon & Tiger / Margin / Money Flow: East Money Datacenter API
- Stock Money Flow: East Money push2 API (requires cookie, see `.cookie` file)
- Concept Sectors: East Money push2 API (no auth required)
```

- [ ] **Step 5: Manual verification**

Open `SKILL.md` and confirm:
- "Concept Sectors (概念板块)" section appears before "Money Flow"
- Scripts table has 7 rows
- Output Fields section has 2 new entries
- Notes section has new "Concept Sectors" line

---

## Task 4: Update AGENTS.md

**Files:**
- Modify: `AGENTS.md` (add command examples)

- [ ] **Step 1: Add Concept Sector section**

Open `AGENTS.md` and find the "### Stock Data Scripts" section. Add a new subsection after "### Cookie Management" and before "## Stock Code Format":

```markdown
### Concept Sectors (概念板块)
```bash
# List all concept sectors (~500+)
python .agents/skills/stock-analysis/scripts/fetch_concept.py
python .agents/skills/stock-analysis/scripts/fetch_concept.py --json
python .agents/skills/stock-analysis/scripts/fetch_concept.py --search "新" --top 20
python .agents/skills/stock-analysis/scripts/fetch_concept.py --csv -o concepts.csv

# Get stocks in a specific concept
python .agents/skills/stock-analysis/scripts/fetch_concept.py --code BK0486
python .agents/skills/stock-analysis/scripts/fetch_concept.py --name "元宇宙"
```

```

- [ ] **Step 2: Manual verification**

Open `AGENTS.md` and confirm:
- New "### Concept Sectors (概念板块)" subsection appears
- Examples follow the same style as other entries in the file
- Code blocks are properly formatted

---

## Task 5: End-to-end smoke test

**Files:** None (verification only)

- [ ] **Step 1: Run all primary use cases**

From the project root, run each of the following and confirm expected behavior:

```bash
# 1. List all concepts
python .agents/skills/stock-analysis/scripts/fetch_concept.py --top 5

# 2. JSON output
python .agents/skills/stock-analysis/scripts/fetch_concept.py --json --top 3

# 3. Search filter
python .agents/skills/stock-analysis/scripts/fetch_concept.py --search "AI"

# 4. Fetch by code (use a real code from the list output)
python .agents/skills/stock-analysis/scripts/fetch_concept.py --code BK0486

# 5. Fetch by name
python .agents/skills/stock-analysis/scripts/fetch_concept.py --name "元宇宙"

# 6. CSV output
python .agents/skills/stock-analysis/scripts/fetch_concept.py --csv --top 3 -o /tmp/test_concepts.csv
cat /tmp/test_concepts.csv
```

**Expected:** All 6 commands succeed. Commands 1, 2, 6 produce concept lists. Commands 3 produces filtered list. Commands 4, 5 produce stock lists with sh/sz/bj prefixes.

- [ ] **Step 2: Verify error cases**

```bash
# Invalid code
python .agents/skills/stock-analysis/scripts/fetch_concept.py --code BK99999
echo "Exit code: $?"

# Invalid name
python .agents/skills/stock-analysis/scripts/fetch_concept.py --name "不存在的概念"
echo "Exit code: $?"

# Conflicting flags
python .agents/skills/stock-analysis/scripts/fetch_concept.py --code BK0486 --name "test"
echo "Exit code: $?"
```

**Expected:** All 3 commands print an error message and exit with code 1.

---

## Self-Review

**Spec coverage:**
- ✅ List all concept sectors → Task 1 (Step 1) + Task 2 (default mode)
- ✅ Get stocks in specific concept by code → Task 1 (Step 2) + Task 2 (--code)
- ✅ Get stocks by name → Task 2 (find_concept_by_name helper)
- ✅ Basic info only (code, name) → All tasks return only `code`, `name`, `source`
- ✅ Output formats (table, JSON, CSV) → Task 2 to_csv_output and table functions
- ✅ SKILL.md update → Task 3
- ✅ AGENTS.md update → Task 4
- ✅ No cookie required → Noted in Task 1 (uses _get_push2_headers but cookie is optional/empty)
- ✅ Out of scope: theme scoring model — Spec correctly excludes it

**Placeholder scan:** No "TBD", "TODO", or vague instructions. All code blocks contain complete, runnable code.

**Type consistency:**
- `fetch_concept_list()` returns `list[dict]` with `code`, `name`, `source` — consistent across all callers
- `fetch_concept_stocks(code: str)` returns `list[dict]` with `code`, `name`, `source` — consistent
- `find_concept_by_name(name: str)` returns `str | None` — used in main() to handle None case
- All `args.code`, `args.name`, `args.search`, `args.top` usage is consistent
