---
title: Build Failures
description: Troubleshooting build process errors and compilation issues
---

# Build Failures — Trace Strategies

Reference for debugging compilation, bundling, and asset errors. Focus: **trace to root cause**, not just read error messages.

---

## Compilation Errors

### TypeScript

**Trace strategy:**
1. **Find the actual error** (not cascading errors):
   - Scroll to FIRST error in output
   - Ignore "X more errors" until first is fixed
   - Look for "TS2304" (not found), "TS2322" (type mismatch), "TS2345" (arg type)

2. **Trace imports**:
   ```bash
   # Find all imports of the failing module
   grep -r "from.*<module-name>" --include="*.ts" --include="*.tsx"
   
   # Check if module exports what's being imported
   grep "export.*<symbol>" path/to/module.ts
   ```

3. **Check type definitions**:
   - Missing: `pnpm add -D @types/<package>`
   - Wrong version: check `package.json` vs `@types/` version
   - Custom types: grep for `.d.ts` files, check `tsconfig.json` "types" array

4. **Trace config**:
   - Read `tsconfig.json` → check `include`, `exclude`, `paths`
   - Check `compilerOptions.moduleResolution` (node vs bundler)
   - Verify `baseUrl` matches project structure

**Common root causes:**
- Circular imports → trace with `madge --circular src/`
- Missing path alias in tsconfig.json
- Import from `src/` when `baseUrl` is not set
- Type-only import used as value (or vice versa)

### Python

**Trace strategy:**
1. **Syntax errors**:
   - Read line number + 1 line before (indentation issues surface late)
   - Check for unclosed brackets/parens/quotes in PRIOR lines
   - Run `python -m py_compile <file>` for precise location

2. **Import errors**:
   ```bash
   # Trace module search path
   python -c "import sys; print('\n'.join(sys.path))"
   
   # Check if module exists
   python -c "import <module>" 2>&1 | grep ModuleNotFoundError
   
   # Find where module is installed
   python -m pip show <package>
   ```

3. **Version conflicts**:
   ```bash
   # Check installed vs required
   pip list | grep <package>
   grep <package> requirements.txt
   
   # Trace dependency tree
   pipdeptree -p <package>
   ```

**Common root causes:**
- Wrong Python version (check `python --version` vs required)
- Virtual env not activated
- Package installed in different env (`where python` on Windows, `which python` on Unix)
- Missing `__init__.py` in package directory

---

## Bundling Errors

### Webpack

**Trace strategy:**
1. **Module not found**:
   ```bash
   # Find all references to missing module
   grep -r "<module-name>" src/
   
   # Check webpack resolve config
   grep -A 10 "resolve:" webpack.config.js
   
   # Verify alias paths
   node -e "console.log(require('path').resolve(__dirname, '<alias-path>'))"
   ```

2. **Loader errors**:
   - Read FULL error (scroll up past stack trace)
   - Check file extension in error vs loader test regex
   - Verify loader order (right to left, bottom to top)
   - Test loader in isolation:
     ```bash
     npx webpack --entry ./src/test-file.ext --mode development
     ```

3. **Plugin failures**:
   - Disable plugins one by one to isolate
   - Check plugin version vs webpack version compatibility
   - Read plugin docs for required config options

**Common root causes:**
- Loader `test` regex doesn't match file extension
- Missing loader dependency (`npm ls <loader-name>`)
- Plugin applied before required data is available (order matters)
- Cache from previous webpack version (`rm -rf node_modules/.cache`)

### Vite

**Trace strategy:**
1. **Dependency pre-bundling errors**:
   ```bash
   # Clear cache and retry
   rm -rf node_modules/.vite
   pnpm dev
   
   # Check which deps are pre-bundled
   grep "Pre-bundling dependencies" output
   
   # Force include/exclude in vite.config
   optimizeDeps: { include: ['pkg'], exclude: ['other'] }
   ```

2. **Import errors**:
   - Vite requires explicit file extensions for relative imports
   - Check if import is missing `.js`/`.ts` extension
   - Verify `resolve.extensions` in config
   - Test raw import:
     ```bash
     node --input-type=module -e "import('./src/file.js')"
     ```

3. **Asset loading**:
   - Check `public/` vs `src/assets/` (public = copy, assets = bundle)
   - Verify `base` path in config matches deployment
   - Test asset URL:
     ```js
     import.meta.url
     new URL('./asset.png', import.meta.url).href
     ```

**Common root causes:**
- ESM-only package imported in CJS context
- Missing `type: "module"` in package.json
- Incorrect `base` path for deployment (should be `/` or `/subdir/`)
- Asset referenced with absolute path instead of relative

### Rollup

**Trace strategy:**
1. **Circular dependency warnings**:
   ```bash
   # Find cycles
   npx madge --circular --extensions ts,tsx src/
   
   # Trace import chain
   npx madge --depends <module> src/
   ```

2. **Unresolved imports**:
   - Check `external` config (should NOT include project code)
   - Verify `@rollup/plugin-node-resolve` is installed
   - Test resolve:
     ```bash
     node -e "require.resolve('<module>')"
     ```

**Common root causes:**
- Node built-ins not marked as external (add `external: ['fs', 'path', ...]`)
- Missing peer dependency
- Import from package's internal path not exported in package.json

---

## Asset Errors

### Missing files

**Trace strategy:**
1. **Find all references**:
   ```bash
   # Search for file path (handle both / and \)
   grep -r "path/to/asset" src/
   grep -r "path\\to\\asset" src/
   
   # Check if file exists
   test -f src/path/to/asset.png && echo "EXISTS" || echo "MISSING"
   ```

2. **Trace copy/move operations**:
   - Check build scripts in package.json
   - Search for `copyfiles`, `cpy`, `fs.copy` in build config
   - Verify `public/` folder structure matches references

3. **Check build output**:
   ```bash
   # List all files in dist
   find dist/ -type f
   
   # Check if asset was copied
   find dist/ -name "asset.png"
   ```

**Common root causes:**
- Asset referenced before build copies it
- Path is relative to wrong base (`/` vs `./` vs `../`)
- Asset in gitignore, not copied to build output
- Filename case mismatch (Mac/Linux case-sensitive)

### Invalid paths

**Trace strategy:**
1. **Check path separators**:
   - Windows: `\` vs `/` (both work in Node, but not all tools)
   - URL paths: always `/`
   - File paths: use `path.join()` or `path.resolve()`

2. **Verify base path**:
   ```bash
   # Check where build thinks root is
   node -e "console.log(__dirname)"
   node -e "console.log(process.cwd())"
   
   # Test absolute path
   node -e "console.log(require('path').resolve('/asset.png'))"
   ```

3. **Trace URL generation**:
   - Check how asset URLs are built in code
   - Verify `publicPath` / `base` config
   - Test in dev vs production (often different)

**Common root causes:**
- Hard-coded absolute paths (use `import.meta.url` or `__dirname`)
- Wrong `publicPath` in webpack config
- CDN URL missing trailing slash
- Path concatenated as string instead of using `path.join()`

---

## Cache Issues

### Stale builds

**Trace strategy:**
1. **Clear all caches**:
   ```bash
   # Node modules cache
   rm -rf node_modules/.cache
   
   # Build tool caches
   rm -rf .vite .next .nuxt dist/ build/
   
   # Package manager cache
   pnpm store prune  # or npm cache clean --force
   
   # TypeScript cache
   rm -rf tsconfig.tsbuildinfo
   ```

2. **Verify clean build**:
   ```bash
   # Full rebuild
   rm -rf dist/ && pnpm build
   
   # Check file timestamps
   ls -la dist/
   ```

3. **Trace cache keys**:
   - Check build tool config for `cache: true`
   - Look for `hash` in output filenames (should change on code change)
   - Verify `package.json` version (some tools cache by version)

**Common root causes:**
- Build tool caching based on stale file hash
- `node_modules` not rebuilt after dependency change
- Browser cache serving old assets (check Network tab, disable cache)
- Docker layer cache not invalidated

### Incremental build errors

**Trace strategy:**
1. **Compare clean vs incremental**:
   ```bash
   # Clean build
   rm -rf dist/ && pnpm build > clean.log 2>&1
   
   # Incremental build
   pnpm build > incremental.log 2>&1
   
   # Diff outputs
   diff clean.log incremental.log
   ```

2. **Bisect the change**:
   - Revert to last working commit
   - Apply changes one file at a time
   - Rebuild after each change
   - Isolate which file breaks incremental build

3. **Check watch mode**:
   - Stop watch process, restart
   - Check for file locks (`lsof <file>` on Unix, `handle <file>` on Windows)
   - Verify file watcher sees changes (`DEBUG=vite:hmr pnpm dev`)

**Common root causes:**
- File watcher not detecting changes (restart IDE)
- Build outputs not cleaned between builds
- Circular dependency only fails on second build
- HMR (hot module reload) state corrupted

---

## General Trace Process

1. **Read the FULL error** (not just last line)
2. **Find the first error** (ignore cascading errors)
3. **Trace the file path** (grep for all references)
4. **Check the config** (tsconfig, webpack, vite, rollup)
5. **Clear caches** (node_modules/.cache, dist/)
6. **Isolate the change** (bisect, disable plugins, minimal repro)
7. **Test in isolation** (compile single file, import single module)

**Do NOT:**
- Skip reading full error output
- Fix cascading errors before root error
- Assume cache is valid
- Change multiple things at once

**DO:**
- Scroll to first error
- Clear caches early
- Test minimal repro
- Check config before code
