# TypeScript & Frontend Optimization Reference

This reference guide provides static analysis tools, refactoring workflows, and React performance optimization guidelines for TypeScript codebases.

---

## 1. Automated Static Analysis Tools & Commands

### Knip (Unused Files, Exports, & Dependencies)
Knip finds unused files, unused exports, unused types, and unused dependencies in JavaScript and TypeScript projects.
```bash
# Run Knip scan
npx knip

# Include production dependencies only
npx knip --production

# Automatically fix fixable unused exports or files
npx knip --fix
```

### TypeScript Compiler (`tsc`)
```bash
# Type check without producing output JavaScript files
npx tsc --noEmit

# Type check with detailed diagnostic timing to locate slow types
npx tsc --noEmit --diagnostics
```

### ESLint & Depcheck
```bash
# Lint code and apply automatic fixes
npx eslint src/ --fix

# Scan for unused package.json dependencies
npx depcheck
```

---

## 2. React & TypeScript Performance Optimization Patterns

### Anti-Pattern 1: Un-Memoized Expensive Calculations & Callbacks
**Problem**: Creating new inline functions or recalculating heavy values on every render breaks `React.memo` and triggers child component re-renders.
**Refactored**:
```tsx
// BAD:
function MatrixBoard({ matrixData, onSelect }: Props) {
  const processedData = matrixData.map(row => expensiveCompute(row)); // Recalculated every render
  return <BoardGrid data={processedData} onClick={() => onSelect()} />;
}

// GOOD:
function MatrixBoard({ matrixData, onSelect }: Props) {
  const processedData = useMemo(() => {
    return matrixData.map(row => expensiveCompute(row));
  }, [matrixData]);

  const handleClick = useCallback(() => {
    onSelect();
  }, [onSelect]);

  return <BoardGrid data={processedData} onClick={handleClick} />;
}
```

### Anti-Pattern 2: Un-Cleaned Side Effects & Memory Leaks
**Problem**: `useEffect` hooks that set up event listeners, timers, or WebSockets without returning a cleanup function cause memory leaks and stale event handlers.
**Refactored**:
```tsx
// BAD:
useEffect(() => {
  const ws = new WebSocket(WS_URL);
  ws.onmessage = (event) => setStatus(event.data);
}, []); // Missing ws.close() on unmount!

// GOOD:
useEffect(() => {
  const ws = new WebSocket(WS_URL);
  ws.onmessage = (event) => setStatus(event.data);

  return () => {
    ws.close();
  };
}, [WS_URL]);
```

### Anti-Pattern 3: Monolithic Library Imports
**Problem**: Importing directly from top-level package index bundles unused modules into the production JavaScript build.
```tsx
// BAD (Pulls in full icon library):
import { Check, X, AlertCircle } from 'lucide-react';

// GOOD (Or ensure bundler tree-shaking is verified in vite.config.ts / tsconfig.json):
import Check from 'lucide-react/dist/esm/icons/check';
```

---

## 3. TypeScript Dead Code & Type Safety Checklist

1. Run `npx knip` in the frontend directory.
2. Review unused exports, types, and files.
3. Verify exports aren't dynamically loaded or used by storybook/test suites.
4. Remove unused code and `package.json` dependencies.
5. Run `npx tsc --noEmit` and `npm run build` to confirm zero build regressions.
