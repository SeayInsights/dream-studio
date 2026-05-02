---
title: Performance Issues
description: Identifying and resolving slowness, memory leaks, and resource bottlenecks
---

# Performance Issues

Strategies for identifying and resolving N+1 queries, memory leaks, and timeout issues.

## N+1 Query Detection

### Database N+1 Patterns

**Symptom:** One query to fetch parent records, then N queries for each child relationship.

```javascript
// BAD: N+1 query pattern
const users = await db.users.findMany();
for (const user of users) {
  const posts = await db.posts.findMany({ where: { userId: user.id } });
  // N queries for posts
}

// GOOD: Eager loading
const users = await db.users.findMany({
  include: { posts: true }
});
```

**Detection Tools:**
- **Prisma:** Set `log: ['query']` in client config
- **Sequelize:** Enable query logging with `logging: console.log`
- **TypeORM:** Set `logging: true` in connection options
- **Raw SQL:** Use `EXPLAIN ANALYZE` to see query execution plan

**Trace Strategy:**
1. Enable query logging in development
2. Monitor query count per request (should be constant, not O(n))
3. Look for repeated similar queries with different IDs
4. Profile with database slow query log

### API N+1 Patterns

**Symptom:** Loop making individual API calls instead of batch request.

```javascript
// BAD: N+1 API calls
const userIds = [1, 2, 3, 4, 5];
for (const id of userIds) {
  const user = await fetch(`/api/users/${id}`);
  // N API calls
}

// GOOD: Batch request
const users = await fetch('/api/users?ids=1,2,3,4,5');
```

**Detection Tools:**
- Browser DevTools Network tab (watch for repeated patterns)
- `axios`/`fetch` interceptors to log requests
- APM tools (Datadog, New Relic) show request waterfall

**Trace Strategy:**
1. Add request interceptor to count calls per component
2. Look for sequential network requests to same endpoint
3. Profile with React DevTools Profiler for render-triggered fetches
4. Use GraphQL batching/DataLoader for multiple entity fetches

## Memory Leak Detection

### Event Listener Leaks

**Symptom:** Event listeners not cleaned up when components unmount.

```javascript
// BAD: Listener never removed
useEffect(() => {
  window.addEventListener('resize', handleResize);
  // Missing cleanup
}, []);

// GOOD: Cleanup on unmount
useEffect(() => {
  window.addEventListener('resize', handleResize);
  return () => window.removeEventListener('resize', handleResize);
}, []);
```

**Detection Tools:**
- Chrome DevTools Memory Profiler
- `getEventListeners(window)` in console
- Heap snapshot comparison (before/after mount/unmount)

**Trace Strategy:**
1. Take heap snapshot before mounting component
2. Mount/unmount component multiple times
3. Take second heap snapshot
4. Compare snapshots - detached DOM nodes indicate leaks
5. Search for event listener objects in retention path

### Closure Memory Leaks

**Symptom:** Closures holding references to large objects or DOM nodes.

```javascript
// BAD: Closure captures entire component state
const handlers = data.map(item => {
  return () => {
    console.log(item, props, state); // Captures everything
  };
});

// GOOD: Only capture needed values
const handlers = data.map(item => {
  const id = item.id; // Extract only what's needed
  return () => console.log(id);
});
```

**Detection Tools:**
- Chrome DevTools Memory > Allocation instrumentation on timeline
- Look for "Retained Size" in heap snapshots
- React DevTools Profiler for component re-renders

**Trace Strategy:**
1. Record allocation timeline during user interaction
2. Stop recording, look for sawtooth pattern (memory not released)
3. Inspect objects with large retained size
4. Check closure scope chain in debugger

### Cache/Store Leaks

**Symptom:** Unbounded cache growth, stores never cleared.

```javascript
// BAD: Cache grows forever
const cache = new Map();
function getData(id) {
  if (!cache.has(id)) {
    cache.set(id, fetchData(id)); // Never evicted
  }
  return cache.get(id);
}

// GOOD: LRU cache with size limit
const cache = new LRUCache({ max: 100 });
```

**Detection Tools:**
- Monitor cache size with custom metrics
- Chrome Memory tab > JS Heap size over time
- APM memory usage graphs

**Trace Strategy:**
1. Add instrumentation to log cache size periodically
2. Monitor memory usage during extended session
3. Look for monotonic memory growth
4. Profile with heap snapshots to find large Map/Set/Array objects
5. Check for WeakMap/WeakRef opportunities for auto-cleanup

## Timeout Debugging

### Blocking I/O Detection

**Symptom:** Synchronous operations block event loop.

```javascript
// BAD: Blocking file read
const data = fs.readFileSync('large-file.json'); // Blocks thread

// GOOD: Async I/O
const data = await fs.promises.readFile('large-file.json');
```

**Detection Tools:**
- Node.js: `--trace-warnings` flag for blocking operations
- `perf_hooks` module to measure event loop lag
- APM tools show request duration breakdown

**Trace Strategy:**
1. Add event loop lag monitoring: `monitorEventLoopDelay()`
2. Look for lag spikes correlating with slow requests
3. Profile with `node --prof` and analyze with `node --prof-process`
4. Check for synchronous crypto, compression, or file operations

### Slow Database Queries

**Symptom:** Queries take too long, timeout before completion.

```sql
-- BAD: Full table scan
SELECT * FROM users WHERE email LIKE '%@gmail.com';

-- GOOD: Indexed query
SELECT * FROM users WHERE email_domain = 'gmail.com';
-- With index on email_domain
```

**Detection Tools:**
- Database slow query log
- `EXPLAIN ANALYZE` for query plan
- APM database query traces

**Trace Strategy:**
1. Enable slow query logging (threshold 100-500ms)
2. Run `EXPLAIN ANALYZE` on slow queries
3. Look for:
   - Full table scans (Seq Scan in Postgres)
   - Missing indexes (Type: ALL in MySQL)
   - Inefficient joins (nested loop on large tables)
   - N+1 patterns (see above)
4. Add indexes, refactor query, or denormalize data

### Infinite Loop/Recursion

**Symptom:** Code never returns, eventually times out.

```javascript
// BAD: Infinite loop
function process(node) {
  process(node.parent); // Missing base case
}

// GOOD: Recursion with base case + depth limit
function process(node, depth = 0) {
  if (!node || depth > 100) return;
  process(node.parent, depth + 1);
}
```

**Detection Tools:**
- Debugger breakpoints in suspected loops
- `console.trace()` to see call stack growth
- CPU profiler shows hot functions

**Trace Strategy:**
1. Add depth counter to recursive functions
2. Log loop iterations (sample every 1000 iterations)
3. Profile with CPU profiler - top function by total time
4. Check for missing base cases, incorrect loop conditions
5. Add circuit breaker with max iterations/depth

## Profiling Tools & Techniques

### Browser Performance Profiling

**Chrome DevTools Performance Tab:**
1. Record during slow interaction
2. Look for long tasks (>50ms)
3. Check Main thread for blocking work
4. Flame chart shows function call hierarchy
5. Bottom-Up view shows total time per function

**React DevTools Profiler:**
1. Record render cycle
2. Ranked chart shows slowest components
3. Flame graph shows component hierarchy with render times
4. Check "Why did this render?" for unnecessary re-renders

### Node.js Performance Profiling

**Built-in Profiler:**
```bash
node --prof app.js
node --prof-process isolate-*-v8.log > profile.txt
```
Analyze `profile.txt` for hot functions.

**Flame Graphs:**
```bash
node --perf-basic-prof app.js
perf record -F 99 -p $(pgrep node) -g -- sleep 30
perf script | stackcollapse-perf.pl | flamegraph.pl > flame.svg
```

**Heap Snapshots (Memory Leaks):**
```javascript
const v8 = require('v8');
const fs = require('fs');

function takeHeapSnapshot() {
  const snapshot = v8.writeHeapSnapshot();
  console.log('Heap snapshot written to', snapshot);
}
```
Compare snapshots before/after to find leaks.

### APM Tools

**Datadog, New Relic, Sentry:**
- Automatic instrumentation for common frameworks
- Request tracing with database query breakdown
- Memory/CPU graphs over time
- Error tracking with stack traces
- Custom metrics for business logic

**Key Metrics to Monitor:**
- P50/P95/P99 response time (detect outliers)
- Apdex score (user satisfaction)
- Error rate (5xx errors)
- Throughput (requests per second)
- Memory usage over time
- CPU usage per request

## Performance Testing Patterns

### Load Testing

```javascript
// k6 load test example
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 }, // Ramp up
    { duration: '5m', target: 100 }, // Sustained load
    { duration: '2m', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% under 500ms
  },
};

export default function() {
  const res = http.get('https://api.example.com/users');
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
```

**Detect issues:**
- Response time increases with load (need scaling/optimization)
- Memory grows during test (memory leak)
- Throughput plateaus (resource bottleneck)

### Synthetic Monitoring

```javascript
// Playwright performance test
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  await page.goto('https://example.com');
  
  const metrics = await page.evaluate(() => {
    const timing = performance.timing;
    return {
      dns: timing.domainLookupEnd - timing.domainLookupStart,
      tcp: timing.connectEnd - timing.connectStart,
      ttfb: timing.responseStart - timing.requestStart,
      download: timing.responseEnd - timing.responseStart,
      domLoaded: timing.domContentLoadedEventEnd - timing.navigationStart,
      pageLoad: timing.loadEventEnd - timing.navigationStart,
    };
  });
  
  console.log('Performance:', metrics);
  await browser.close();
})();
```

## Quick Reference Checklist

**N+1 Queries:**
- [ ] Enable query logging
- [ ] Count queries per request
- [ ] Use eager loading/joins
- [ ] Batch API requests
- [ ] Consider GraphQL DataLoader

**Memory Leaks:**
- [ ] Clean up event listeners
- [ ] Avoid large closures
- [ ] Bound cache sizes
- [ ] Take heap snapshots
- [ ] Profile detached DOM nodes

**Timeouts:**
- [ ] Use async I/O
- [ ] Optimize database indexes
- [ ] Add recursion depth limits
- [ ] Monitor event loop lag
- [ ] Profile CPU usage

**General:**
- [ ] Profile before optimizing
- [ ] Set performance budgets
- [ ] Monitor in production
- [ ] Load test before launch
- [ ] Document performance requirements
