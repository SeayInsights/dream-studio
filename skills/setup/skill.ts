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
 * Detect if gh CLI is installed
 * To be implemented in T013
 */
export async function detectGh(): Promise<ToolStatus> {
  // TODO: Cross-platform detection
  // Windows: where gh
  // Unix: which gh
  // Return {installed: bool, version: string|null, path: string|null}
  throw new Error("Not implemented - see T013");
}

/**
 * Detect if Firecrawl is installed
 * To be implemented in T013
 */
export async function detectFirecrawl(): Promise<ToolStatus> {
  // TODO: Check for Firecrawl CLI or API
  // Verify with --version or API connectivity check
  throw new Error("Not implemented - see T013");
}

/**
 * Detect if Playwright is installed
 * To be implemented in T013
 */
export async function detectPlaywright(): Promise<ToolStatus> {
  // TODO: Check npm registry for @playwright/test
  // Or check local node_modules
  throw new Error("Not implemented - see T013");
}

/**
 * Generic tool detection function
 * To be implemented as part of T013
 */
export async function detectTool(toolName: string): Promise<ToolStatus> {
  // TODO: Delegate to tool-specific detection functions
  // Support: gh, firecrawl, playwright, npm, python, node
  throw new Error("Not implemented - see T013");
}
