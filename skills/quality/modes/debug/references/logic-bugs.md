---
title: Logic Bugs
description: Debugging incorrect behavior, state management issues, and business logic errors
---

# Logic Bugs

Logic bugs are the hardest to debug because they represent flaws in reasoning rather than syntax errors. They require systematic tracing of program state and control flow.

## Concurrency

Race conditions, deadlocks, and async issues emerge from incorrect timing assumptions.

### Race Conditions

**Symptoms:**
- Intermittent failures that disappear when adding logging
- Different behavior in dev vs production
- Bugs that only appear under load
- Non-deterministic test failures

**Trace Strategy:**

1. **Identify shared state:**
   - What variables/resources are accessed by multiple threads/processes?
   - What data crosses async boundaries?
   - What caches or singletons exist?

2. **Map access patterns:**
   - Who reads this state? When?
   - Who writes this state? When?
   - Are reads/writes atomic?
   - What assumptions exist about ordering?

3. **Find unsynchronized access:**
   ```
   Thread A: read counter → increment → write counter
   Thread B: read counter → increment → write counter
   
   Expected: counter += 2
   Actual: counter += 1 (lost update)
   ```

4. **Trace the critical section:**
   - Add timestamps to all state mutations
   - Log thread/coroutine IDs
   - Check for "check-then-act" patterns (time-of-check vs time-of-use)

**Resolution Patterns:**
- Add locks/mutexes around critical sections
- Use atomic operations
- Implement optimistic locking (compare-and-swap)
- Eliminate shared mutable state

### Deadlocks

**Symptoms:**
- Application hangs indefinitely
- CPU usage drops to zero while waiting
- Progress stops at consistent points

**Trace Strategy:**

1. **Map lock acquisition order:**
   ```
   Thread A: lock(X) → lock(Y)
   Thread B: lock(Y) → lock(X)
   
   Result: circular wait (deadlock)
   ```

2. **Identify wait chains:**
   - What is each thread waiting for?
   - Who holds the resource each thread needs?
   - Is there a cycle in the dependency graph?

3. **Check for nested locking:**
   - Does code acquire multiple locks?
   - Is the order consistent across all code paths?
   - Are locks released in reverse order?

4. **Look for missing timeouts:**
   - Do all lock acquisitions have timeouts?
   - What happens when a timeout occurs?

**Resolution Patterns:**
- Enforce global lock ordering
- Use lock hierarchies
- Implement timeout + retry with backoff
- Redesign to avoid holding multiple locks

### Async/Await Issues

**Symptoms:**
- Promises never resolve
- Callbacks not firing
- "Unhandled promise rejection" errors
- Mixed sync/async behavior

**Trace Strategy:**

1. **Track promise chains:**
   ```javascript
   fetchData()
     .then(processData)  // ← Does this return a promise?
     .then(saveResult)   // ← Or undefined?
   ```

2. **Check error propagation:**
   - Is every promise rejection caught?
   - Do catch blocks re-throw or return?
   - Are async functions wrapped in try/catch?

3. **Verify await placement:**
   ```javascript
   async function bad() {
     doAsync();        // Forgot await - fires and forgets
     return result;    // Uses stale data
   }
   ```

4. **Look for event loop blocking:**
   - Are CPU-intensive operations blocking the event loop?
   - Should long operations be moved to workers?

**Resolution Patterns:**
- Always return promises from `.then()` handlers
- Use `Promise.all()` for parallel operations
- Add `.catch()` to every promise chain
- Use async/await consistently (don't mix with callbacks)

## Edge Cases

Boundary conditions and unexpected inputs expose incorrect assumptions.

### Boundary Conditions

**Symptoms:**
- Off-by-one errors in loops/arrays
- Failures at min/max values
- Wrong behavior at boundaries (0, empty, null)

**Trace Strategy:**

1. **Test boundary values systematically:**
   ```
   For numeric ranges [min, max]:
   - min - 1 (below range)
   - min (lower boundary)
   - min + 1 (just inside)
   - max - 1 (just inside)
   - max (upper boundary)
   - max + 1 (above range)
   ```

2. **Check loop conditions:**
   ```javascript
   for (let i = 0; i < arr.length; i++)  // vs i <= arr.length (off-by-one)
   ```

3. **Verify slice/substring logic:**
   - Is the end index inclusive or exclusive?
   - What happens with negative indices?
   - How does the language handle out-of-bounds access?

4. **Test empty collections:**
   - Empty arrays: `[]`
   - Empty strings: `""`
   - Empty maps/sets: `new Map()`
   - What's returned from `.first()` on empty collection?

**Resolution Patterns:**
- Write boundary tests before implementation
- Use inclusive ranges where possible (avoid off-by-one)
- Add guards for empty inputs
- Prefer iteration patterns that handle empty collections (forEach, map)

### Null/Undefined Handling

**Symptoms:**
- "Cannot read property of undefined"
- Null pointer exceptions
- Silent failures when values are missing

**Trace Strategy:**

1. **Trace nullable origins:**
   - Where can null/undefined enter the system?
   - API responses, database queries, user input
   - Optional parameters, missing config values

2. **Map propagation paths:**
   ```javascript
   const user = getUser(id);      // May return null
   const name = user.profile.name; // Crashes if user is null
   ```

3. **Check default value handling:**
   - Are defaults applied at the source or at usage?
   - Do defaults handle all nullable cases?
   - Are defaults appropriate for the context?

4. **Identify missing validation:**
   - Where should null checks exist?
   - Are checks at boundaries (API entry points)?
   - Or scattered throughout codebase?

**Resolution Patterns:**
- Use optional chaining: `user?.profile?.name`
- Apply nullish coalescing: `value ?? defaultValue`
- Validate at boundaries (fail fast)
- Use type systems to track nullability (TypeScript strict null checks)

### Integer Overflow/Precision Loss

**Symptoms:**
- Negative values appearing unexpectedly
- Precision loss in calculations
- Wrap-around behavior

**Trace Strategy:**

1. **Check numeric limits:**
   ```javascript
   Number.MAX_SAFE_INTEGER = 9007199254740991
   // Anything larger loses precision in JavaScript
   ```

2. **Trace calculation chains:**
   - What intermediate values are computed?
   - Can any step exceed safe limits?
   - Are calculations performed in the right order?

3. **Test with extreme values:**
   - Maximum possible inputs
   - Products/sums of large numbers
   - Division by very small numbers (precision loss)

**Resolution Patterns:**
- Use BigInt for large integers
- Use decimal libraries for financial calculations
- Add overflow checks before operations
- Normalize ranges to prevent overflow

## State Bugs

Incorrect state management causes systems to reach invalid states.

### State Transition Errors

**Symptoms:**
- Invalid state combinations
- Actions available when they shouldn't be
- States that can't be reached or exited

**Trace Strategy:**

1. **Map the state machine:**
   ```
   States: [idle, loading, success, error]
   Transitions:
     idle → loading (on fetch)
     loading → success (on data)
     loading → error (on failure)
     success → loading (on refetch)
     error → loading (on retry)
   ```

2. **Find impossible states:**
   ```javascript
   // Bad: both flags can be true
   { isLoading: true, isSuccess: true }
   
   // Good: mutually exclusive states
   { status: 'loading' | 'success' | 'error' }
   ```

3. **Check missing transitions:**
   - Can every state be exited?
   - Are all valid transitions implemented?
   - What happens on unexpected events?

4. **Verify invariants:**
   - What must always be true in each state?
   - Are invariants enforced after every transition?

**Resolution Patterns:**
- Use tagged unions for mutually exclusive states
- Implement state machines explicitly (XState, etc.)
- Add assertions for state invariants
- Make invalid states unrepresentable

### Stale State

**Symptoms:**
- UI showing outdated data
- Cache returning old values
- Components not re-rendering

**Trace Strategy:**

1. **Track data flow:**
   ```
   Source → Cache → Component → UI
   
   Where can staleness occur?
   - Cache not invalidated
   - Component not subscribed to updates
   - UI not bound to reactive state
   ```

2. **Check invalidation logic:**
   - When should cached data be cleared?
   - Are all mutation points covered?
   - Is there a TTL/expiry mechanism?

3. **Verify reactivity:**
   - Is state mutated in place (breaks reactivity)?
   - Are updates triggering re-renders?
   - Are dependencies tracked correctly?

4. **Look for snapshot issues:**
   ```javascript
   // Closure captures old value
   setTimeout(() => {
     console.log(count); // Stale
   }, 1000);
   ```

**Resolution Patterns:**
- Immutable updates (create new objects)
- Invalidate cache on mutations
- Use reactive primitives (signals, observables)
- Implement cache versioning/tagging

### Unintended Mutations

**Symptoms:**
- Object properties changing unexpectedly
- Array contents modified by surprise
- Reference sharing causing side effects

**Trace Strategy:**

1. **Find mutation sites:**
   ```javascript
   function processUser(user) {
     user.lastSeen = Date.now(); // Mutates parameter!
     return user;
   }
   ```

2. **Check for shared references:**
   ```javascript
   const defaults = { theme: 'dark' };
   const userA = defaults; // Same object
   const userB = defaults; // Same object
   userA.theme = 'light';  // Affects userB too
   ```

3. **Look for shallow copies:**
   ```javascript
   const copy = { ...original }; // Shallow
   copy.nested.value = 'x';      // Mutates original.nested
   ```

4. **Trace pass-by-reference:**
   - What objects are passed to functions?
   - Are they copied or mutated in place?
   - Do functions have side effects?

**Resolution Patterns:**
- Use `Object.freeze()` for immutability
- Deep clone before mutating
- Return new objects instead of mutating
- Use immutable data structures (Immer, Immutable.js)

### State Synchronization Issues

**Symptoms:**
- Client and server out of sync
- Multiple sources of truth disagree
- Optimistic updates not rolled back on failure

**Trace Strategy:**

1. **Identify sources of truth:**
   - What is the authoritative source?
   - Where are copies/caches?
   - How is sync triggered?

2. **Map update flows:**
   ```
   User action → Optimistic update → API call → Success/Failure
                                                      ↓
                                                 Confirm or Rollback
   ```

3. **Check for missing rollbacks:**
   - What happens if the API call fails?
   - Is the optimistic update reverted?
   - Are error states communicated?

4. **Look for partial updates:**
   - Are all related fields updated together?
   - Can state become inconsistent mid-update?

**Resolution Patterns:**
- Single source of truth (server-authoritative)
- Version numbers or ETags for conflict detection
- Transaction-based updates (all-or-nothing)
- Event sourcing for audit trail

---

## General Logic Bug Strategy

1. **Reproduce reliably** - Can't fix what you can't reproduce
2. **Minimize the test case** - Remove everything unrelated to the bug
3. **Form a hypothesis** - What do you think is wrong?
4. **Add observability** - Logs, traces, assertions to test hypothesis
5. **Verify the fix** - Does the minimal test case now pass?
6. **Prevent regression** - Add automated test for this scenario
