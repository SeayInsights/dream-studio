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
 * To be implemented in T004
 */
export async function isFirstRun(): Promise<boolean> {
  // TODO: Check if .dream-studio/setup-prefs.json exists
  // Return true if missing, false if exists
  throw new Error("Not implemented - see T004");
}

/**
 * Display first-run prompt and capture user choice
 * To be implemented in T005
 */
export async function promptForSetupPath(): Promise<"wizard" | "as-needed" | "read-docs"> {
  // TODO: Display prompt with three options
  // Return user's choice
  throw new Error("Not implemented - see T005");
}

/**
 * Save setup preferences to .dream-studio/setup-prefs.json
 * To be implemented in T006
 */
export async function savePreference(prefs: SetupPreferences): Promise<void> {
  // TODO: Write to .dream-studio/setup-prefs.json
  // Create .dream-studio directory if it doesn't exist
  throw new Error("Not implemented - see T006");
}

/**
 * Load setup preferences from .dream-studio/setup-prefs.json
 * To be implemented in T006
 */
export async function loadPreference(): Promise<SetupPreferences | null> {
  // TODO: Read from .dream-studio/setup-prefs.json
  // Return null if file doesn't exist
  throw new Error("Not implemented - see T006");
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
