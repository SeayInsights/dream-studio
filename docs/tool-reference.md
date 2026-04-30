# Tool Reference

Per-tool documentation for the 6 optional tools that extend dream-studio capabilities. The SSOT for tool metadata is [`skills/setup/tool-registry.yml`](../skills/setup/tool-registry.yml).

---

## Overview

| Tool | What it is | Required? | Verification |
|------|-----------|-----------|--------------|
| [gh](#gh--github-cli) | GitHub CLI | Recommended | `gh --version` |
| [firecrawl](#firecrawl) | Web scraping / LLM extraction (MCP server) | Optional | `claude mcp list` shows `firecrawl-mcp` |
| [playwright](#playwright) | Browser automation and UI testing | Optional | `playwright --version` |
| [npm](#npm--node-package-manager) | JavaScript package manager | Optional | `npm --version` |
| [python](#python) | Python interpreter | Required | `python --version` |
| [node](#nodejs) | JavaScript runtime | Optional | `node --version` |

---

## gh — GitHub CLI

**What it is:** Official GitHub command-line interface for managing repositories, issues, pull requests, and Actions workflows.

**Why you'd want it:** dream-studio uses `gh` for all GitHub operations — creating issues, branches, PRs, and merging. Without it, the Issue → PR workflow described in CLAUDE.md cannot execute, and the git-based build lifecycle (`core:ship`, `core:review`) loses its automation.

**Which skills benefit:**

| Pack | Mode | What it enables |
|------|------|----------------|
| `dream-studio:core` | `build`, `review`, `ship` | PR creation, review, and merge automation |
| `dream-studio:core` | `handoff` | Branch and PR state inspection |
| `dream-studio:domains` | `client-work` | GitHub integration for client repos |
| `dream-studio:quality` | `debug` | Issue creation as part of debug workflow |

**Install:**

| Platform | Command |
|----------|---------|
| Windows | `choco install gh -y` |
| macOS | `brew install gh` |
| Linux | `sudo apt-get install gh` |

**Verify:** `gh --version`

**Docs:** https://cli.github.com/manual

---

## firecrawl

**What it is:** MCP server for web scraping, crawling, search, and LLM-ready data extraction via the Firecrawl API.

**Why you'd want it:** Enables dream-studio to fetch, crawl, search, and convert web pages into structured content for research, security analysis, and client data gathering. Runs as an MCP server inside Claude Code — tools appear automatically as `mcp__firecrawl-mcp__*` when connected.

**Which skills benefit:**

| Pack | Mode | What it enables |
|------|------|----------------|
| `dream-studio:core` | `think` | Web research and content extraction for specs |
| `dream-studio:domains` | `client-work` | Scraping client data sources and web reports |
| `dream-studio:security` | `dast` | Site crawling and DAST findings extraction |
| `dream-studio:career` | `scan` | Job portal scraping via firecrawl_search |

**Install:**

```bash
claude mcp add --scope user firecrawl-mcp -e FIRECRAWL_API_KEY=<your-key> -- npx -y firecrawl-mcp
```

Or install globally and point Claude Code to it:

```bash
npm install -g firecrawl-mcp
claude mcp add --scope user firecrawl-mcp -e FIRECRAWL_API_KEY=<your-key> -- node "$(npm root -g)/firecrawl-mcp/dist/index.js"
```

**API key:** Required. Get one at [firecrawl.dev](https://firecrawl.dev). Pass via `-e FIRECRAWL_API_KEY=<key>` in the `claude mcp add` command.

**Verify:** `claude mcp list` — should show `firecrawl-mcp: connected`

**Docs:** https://github.com/mendableai/firecrawl-mcp-server

---

## playwright

**What it is:** Browser automation framework for headless testing, screenshot capture, and dynamic page interaction.

**Why you'd want it:** Enables UI verification screenshots during builds, browser-based security testing (DAST), and automated regression checks for web apps. The `quality:polish` and `domains:saas-build` modes use it to confirm visual output without a manual browser step.

**Which skills benefit:**

| Pack | Mode | What it enables |
|------|------|----------------|
| `dream-studio:quality` | `polish`, `debug` | Screenshot capture and UI regression checks |
| `dream-studio:security` | `dast` | Browser-driven vulnerability scanning |
| `dream-studio:domains` | `saas-build` | Automated UI testing for SaaS features |

**Install:**

| Platform | Command |
|----------|---------|
| Windows | `pip install playwright && playwright install` |
| macOS | `pip install playwright && playwright install` |
| Linux | `pip install playwright && playwright install` |

**Verify:** `playwright --version`

**Docs:** https://playwright.dev

---

## npm — Node Package Manager

**What it is:** JavaScript and TypeScript package manager for installing, managing, and running Node.js dependencies.

**Why you'd want it:** Required for any project using a Node.js-based stack. `domains:saas-build` (React 19, Cloudflare Workers) and frontend toolchains depend on npm to install packages and run build scripts.

**Which skills benefit:**

| Pack | Mode | What it enables |
|------|------|----------------|
| `dream-studio:domains` | `saas-build`, `dashboard-dev` | Frontend package installs, build scripts |
| `dream-studio:workflow` | (all) | Package script execution in CI/workflow steps |
| `dream-studio:domains` | `mcp-build` | Node-based MCP server scaffolding |

**Install:**

| Platform | Command |
|----------|---------|
| Windows | `choco install nodejs -y` (includes npm) |
| macOS | `brew install node` (includes npm) |
| Linux | `sudo apt-get install nodejs npm` |

**Verify:** `npm --version`

**Docs:** https://docs.npmjs.com

---

## python

**What it is:** Python interpreter and runtime. The core runtime dependency for dream-studio itself.

**Why you'd want it:** dream-studio is a Python-based framework — virtually every pack and mode depends on it. Scripts in `scripts/`, hooks, YAML validation, and test suites all require Python 3.10+. Recommended version: **3.12** (3.14 may have compatibility gaps with some dependencies).

**Which skills benefit:**

| Pack | Mode | What it enables |
|------|------|----------------|
| `dream-studio:core` | all | Core pipeline execution |
| `dream-studio:quality` | `debug`, `harden`, `secure` | Linting, formatting, test runners |
| `dream-studio:security` | `scan`, `binary-scan` | Vulnerability scanning, binary analysis |
| All packs | all | Core runtime — nothing works without it |

**Install:**

| Platform | Command |
|----------|---------|
| Windows | `choco install python -y` |
| macOS | `brew install python@3.12` |
| Linux | `sudo apt-get install python3.12 python3.12-venv` |

**Verify:** `python --version` (Windows: `py --version`)

**Docs:** https://www.python.org/downloads

---

## Node.js

**What it is:** JavaScript runtime for executing Node.js scripts, CLI tools, and server-side applications.

**Why you'd want it:** Underpins all JavaScript-based tooling. Required when building SaaS features (Cloudflare Workers, React apps), MCP servers in TypeScript, or any skill that shells out to a Node-based CLI. npm ships with Node — installing Node gives you both.

**Which skills benefit:**

| Pack | Mode | What it enables |
|------|------|----------------|
| `dream-studio:domains` | `saas-build` | Cloudflare Workers, React 19 builds |
| `dream-studio:domains` | `mcp-build` | TypeScript MCP server execution |
| `dream-studio:workflow` | (all) | Node-based CLI tools and scripts |
| Frontend tooling | — | Vite, esbuild, and other build systems |

**Install:**

| Platform | Command |
|----------|---------|
| Windows | `choco install nodejs -y` |
| macOS | `brew install node` |
| Linux | `sudo apt-get install nodejs` |

**Verify:** `node --version`

**Docs:** https://nodejs.org/en/download

---

## Setup Profiles

For recommended tool combinations based on your use case, see the [Setup Profiles](../README.md#setup-profiles) section in the main README.
