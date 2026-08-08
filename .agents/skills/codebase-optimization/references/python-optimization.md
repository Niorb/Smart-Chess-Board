# Python Optimization & Code Quality Reference

This reference guide details specific patterns, tool configurations, and performance techniques for reviewing and optimizing Python code bases.

---

## 1. Automated Static Analysis Tools & Commands

### Ruff (Linter & Formatter)
Ruff replaces `flake8`, `isort`, `black`, `pyupgrade`, `pydocstyle`, and `bandit`.
```bash
# Check code style and common bugs
ruff check .

# Automatically fix fixable issues (imports, syntax modernizations)
ruff check --fix .

# Select specific rule categories:
# F = Pyflakes, E/W = pycodestyle, I = isort, UP = pyupgrade, B = flake8-bugbear, SIM = flake8-simplify
ruff check . --select F,E,W,I,UP,B,SIM
```

### Vulture (Dead Code Detection)
Vulture scans Python programs for unused functions, classes, methods, properties, variables, and imports using standard library `ast`.
```bash
# Basic dead code scan
vulture .

# Scan with confidence threshold (80% confidence or higher)
vulture Raspberry/ --min-confidence 80

# Ignore false positives by creating a whitelist file:
vulture Raspberry/ --make-whitelist > .vulture_whitelist.py
```

### Mypy & Pyright (Static Type Checking)
```bash
# Mypy type check
mypy Raspberry/ --ignore-missing-imports --strict-optional

# Pyright type check
npx pyright
```

### Radon & Xenon (Complexity Auditing)
```bash
# Measure Cyclomatic Complexity (A = best, F = worst)
radon cc . -a -s

# Assert complexity thresholds in CI (fail if complexity > B)
xenon --max-absolute B --max-modules A --max-average A .
```

---

## 2. Common Python Sub-Optimal Anti-Patterns & Refactorings

### Anti-Pattern 1: Blocking I/O inside AsyncIO Loops
**Problem**: Calling `time.sleep()`, synchronous `requests.get()`, or blocking serial `read()` inside `async def` halts the entire event loop.
**Refactored**:
```python
# BAD:
async def handle_request():
    time.sleep(1) # Blocks all concurrent requests
    res = requests.get("https://api.example.com/data")

# GOOD:
async def handle_request():
    await asyncio.sleep(1)
    async with httpx.AsyncClient() as client:
        res = await client.get("https://api.example.com/data")

# GOOD (for CPU-bound or legacy synchronous blocking calls):
async def handle_legacy():
    res = await asyncio.to_thread(sync_blocking_function)
```

### Anti-Pattern 2: Inefficient Lookups (`O(N)` vs `O(1)`)
**Problem**: Checking membership in a list inside a loop.
```python
# BAD (O(N) lookup per iteration):
allowed_users = ["alice", "bob", "charlie", "david"]
for item in active_requests:
    if item in allowed_users:
        process(item)

# GOOD (O(1) set lookup):
allowed_users = {"alice", "bob", "charlie", "david"}
for item in active_requests:
    if item in allowed_users:
        process(item)
```

### Anti-Pattern 3: Temporary Allocations in Aggregations
**Problem**: Building an intermediate list before passing to `sum`, `min`, `max`, or `any`.
```python
# BAD (Allocates full list in memory):
total_score = sum([item.score for item in heavy_dataset])

# GOOD (Uses generator expression, O(1) extra space):
total_score = sum(item.score for item in heavy_dataset)
```

### Anti-Pattern 4: Repeated String Concatenation in Loops
**Problem**: Using `+=` to build strings in loops allocates new string objects every iteration (`O(N^2)`).
```python
# BAD:
output = ""
for chunk in chunks:
    output += chunk

# GOOD:
output = "".join(chunks)
```

---

## 3. Python Dead Code Elimination Checklist

1. Run `vulture . --min-confidence 80`.
2. Inspect listed unused symbols.
3. Check if symbols are dynamically invoked (e.g. FastAPI routes, WebSocket message types, dynamic `getattr()`, or test fixtures).
4. Remove confirmed dead functions, unused arguments, and obsolete imports.
5. Re-run `pytest` to ensure zero breakage.
