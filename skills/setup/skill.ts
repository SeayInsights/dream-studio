/**
 * dream-studio:setup skill — First-run experience and tool management
 *
 * This module implements:
 * - First-run detection (checks if .dream-studio/setup-prefs.json exists)
 * - Preference persistence (savePreference, loadPreference)
 * - Tool detection (detectGh, detectFirecrawl, detectPlaywright, etc.)
 * - Setup modes (wizard, status, jit)
 *
 * To be implemented in tasks:
 * - T004: First-run detection logic (isFirstRun)
 * - T005: First-run prompt (promptForSetupPath)
 * - T006: Preference save/load (savePreference, loadPreference)
 * - T013: Tool-specific detection functions (detectGh, detectFirecrawl, etc.)
 * - T010-T020: Mode implementations
 */

import { promises as fs } from "fs";
import * as path from "path";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

/** Returns the platform-specific command to locate an executable by name. */
function whichCommand(bin: string): string {
  return process.platform === "win32" ? `where ${bin}` : `which ${bin}`;
}

/**
 * Core helper: locate a binary and verify its version.
 * @param bin         The executable name (e.g. "gh", "node").
 * @param versionArg  The flag used to print the version (default: "--version").
 * @param parseVersion Optional function to extract a clean semver from raw output.
 */
async function detectBinary(
  bin: string,
  versionArg = "--version",
  parseVersion?: (raw: string) => string | null,
): Promise<ToolStatus> {
  // Step 1 — locate the binary
  let binPath: string | null = null;
  try {
    const { stdout } = await execAsync(whichCommand(bin));
    // `where` on Windows may return multiple lines; use the first one
    binPath = stdout.split(/\r?\n/)[0].trim() || null;
  } catch {
    return { installed: false, version: null, path: null };
  }

  // Step 2 — check version
  let version: string | null = null;
  try {
    const { stdout } = await execAsync(`${bin} ${versionArg}`);
    const raw = stdout.trim();
    version = parseVersion ? parseVersion(raw) : raw.split(/\r?\n/)[0] || null;
  } catch {
    // Binary exists but --version failed — still mark as installed
  }

  return { installed: true, version, path: binPath };
}

export interface SetupPreferences {
  onboarding_path: "wizard" | "as-needed" | "read-docs";
  first_run_complete: boolean;
  tools: {
    [toolName: string]: {
      installed: boolean;
      version?: string | null;
      path?: string | null;
      skipped?: boolean;
      never_prompt?: boolean;
    };
  };
}

export interface ToolStatus {
  installed: boolean;
  version: string | null;
  path: string | null;
}

/**
 * Check if this is the first run (setup-prefs.json doesn't exist)
 * Implemented in T004
 */
export async function isFirstRun(): Promise<boolean> {
  const prefsPath = path.join(process.cwd(), ".dream-studio", "setup-prefs.json");

  try {
    await fs.access(prefsPath);
    return false; // File exists
  } catch {
    return true; // File doesn't exist (or directory doesn't exist)
  }
}

/**
 * Display first-run prompt and capture user choice
 * Implemented in T005
 */
export async function promptForSetupPath(): Promise<"wizard" | "as-needed" | "read-docs"> {
  const readline = await import("readline");
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log("\n🎉 First time using dream-studio!\n");
  console.log("Choose your setup path:\n");
  console.log("  [1] wizard      - Full interactive setup (detects tools, offers installation)");
  console.log("  [2] as-needed   - Just-in-time prompts when skills need missing tools");
  console.log("  [3] read-docs   - No prompts, I'll read README and install manually\n");

  const validChoices = new Map<string, "wizard" | "as-needed" | "read-docs">([
    ["1", "wizard"],
    ["wizard", "wizard"],
    ["2", "as-needed"],
    ["as-needed", "as-needed"],
    ["3", "read-docs"],
    ["read-docs", "read-docs"],
  ]);

  const getUserChoice = (): Promise<"wizard" | "as-needed" | "read-docs"> => {
    return new Promise((resolve) => {
      rl.question("Enter your choice [1/2/3 or wizard/as-needed/read-docs]: ", (answer) => {
        const normalized = answer.trim().toLowerCase();
        const choice = validChoices.get(normalized);

        if (choice) {
          rl.close();
          resolve(choice);
        } else {
          console.log(`\n❌ Invalid choice: "${answer}". Please enter 1, 2, 3, wizard, as-needed, or read-docs.\n`);
          resolve(getUserChoice());
        }
      });
    });
  };

  return getUserChoice();
}

/**
 * Save setup preferences to .dream-studio/setup-prefs.json
 * Implemented in T006
 */
export async function savePreference(prefs: SetupPreferences): Promise<void> {
  const dreamStudioDir = path.join(process.cwd(), ".dream-studio");
  const prefsPath = path.join(dreamStudioDir, "setup-prefs.json");

  // Create .dream-studio directory if it doesn't exist
  await fs.mkdir(dreamStudioDir, { recursive: true });

  // Write preferences to file
  const jsonContent = JSON.stringify(prefs, null, 2);
  await fs.writeFile(prefsPath, jsonContent, "utf-8");
}

/**
 * Load setup preferences from .dream-studio/setup-prefs.json
 * Implemented in T006
 */
export async function loadPreference(): Promise<SetupPreferences | null> {
  const prefsPath = path.join(process.cwd(), ".dream-studio", "setup-prefs.json");

  try {
    const fileContent = await fs.readFile(prefsPath, "utf-8");
    const prefs = JSON.parse(fileContent) as SetupPreferences;
    return prefs;
  } catch (error) {
    // Return null if file doesn't exist or can't be read
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    // Re-throw other errors (e.g., invalid JSON)
    throw error;
  }
}

/**
 * Detect if gh CLI is installed.
 * Parses output like "gh version 2.47.0 (2024-03-19)" → "2.47.0"
 */
export async function detectGh(): Promise<ToolStatus> {
  return detectBinary("gh", "--version", (raw) => {
    const m = raw.match(/gh version (\S+)/i);
    return m ? m[1] : raw.split(/\r?\n/)[0] || null;
  });
}

/**
 * Detect if Firecrawl CLI is installed.
 * Tries the `firecrawl` binary; falls back to the `@mendable/firecrawl-js`
 * package in local node_modules (npm-installed SDK, no standalone CLI binary).
 */
export async function detectFirecrawl(): Promise<ToolStatus> {
  // Try the CLI binary first
  const cliBinary = await detectBinary("firecrawl", "--version");
  if (cliBinary.installed) return cliBinary;

  // Fall back: check for the npm package in the closest node_modules
  try {
    const pkgPath = require.resolve("@mendable/firecrawl-js/package.json");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const pkg = require(pkgPath) as { version?: string };
    return { installed: true, version: pkg.version ?? null, path: pkgPath };
  } catch {
    // Not found anywhere
    return { installed: false, version: null, path: null };
  }
}

/**
 * Detect if Playwright is installed.
 * Checks for the `@playwright/test` npm package; also tries the `playwright`
 * CLI binary (available after `npm install -g playwright`).
 */
export async function detectPlaywright(): Promise<ToolStatus> {
  // Try the `playwright` CLI binary first (global install)
  const cliBinary = await detectBinary("playwright", "--version", (raw) => {
    const m = raw.match(/Version (\S+)/i);
    return m ? m[1] : raw.split(/\r?\n/)[0] || null;
  });
  if (cliBinary.installed) return cliBinary;

  // Fall back: local node_modules package
  try {
    const pkgPath = require.resolve("@playwright/test/package.json");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const pkg = require(pkgPath) as { version?: string };
    return { installed: true, version: pkg.version ?? null, path: pkgPath };
  } catch {
    // Not found anywhere
    return { installed: false, version: null, path: null };
  }
}

/** Detect Node.js — parses "v20.11.0" style output. */
async function detectNode(): Promise<ToolStatus> {
  return detectBinary("node", "--version", (raw) => raw.replace(/^v/i, "").trim() || null);
}

/** Detect npm — parses plain semver output ("10.5.0"). */
async function detectNpm(): Promise<ToolStatus> {
  return detectBinary("npm", "--version");
}

/** Detect Python — tries `py` (Windows launcher) then `python3` then `python`. */
async function detectPython(): Promise<ToolStatus> {
  const parseVer = (raw: string) => {
    const m = raw.match(/Python (\S+)/i);
    return m ? m[1] : raw.split(/\r?\n/)[0] || null;
  };

  if (process.platform === "win32") {
    const pyLauncher = await detectBinary("py", "--version", parseVer);
    if (pyLauncher.installed) return pyLauncher;
  }

  const py3 = await detectBinary("python3", "--version", parseVer);
  if (py3.installed) return py3;

  return detectBinary("python", "--version", parseVer);
}

/**
 * Generic tool detection dispatcher.
 * Supported tool names: gh, firecrawl, playwright, node, npm, python
 */
export async function detectTool(toolName: string): Promise<ToolStatus> {
  switch (toolName.toLowerCase()) {
    case "gh":
      return detectGh();
    case "firecrawl":
      return detectFirecrawl();
    case "playwright":
      return detectPlaywright();
    case "node":
      return detectNode();
    case "npm":
      return detectNpm();
    case "python":
    case "python3":
      return detectPython();
    default:
      // Generic fallback for unknown tools
      return detectBinary(toolName, "--version");
  }
}
