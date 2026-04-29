# Component Library Patterns

UI component reference for React SaaS builds — shadcn-style primitives, page layout components, and component registry patterns. Sourced from: ANUXR4G/Mage-UI.

---

## 1. UI Primitives

shadcn/ui-compatible components. Install via CLI or copy source — each component is a standalone file, not a monolithic package.

### Interactive primitives
| Component | Use case | Key prop |
|-----------|---------|---------|
| `Accordion` | Collapsible Q&A, FAQ sections | `type="single"` or `"multiple"` |
| `Dialog` | Modal overlays, confirmations | `open` / `onOpenChange` |
| `Dropdown Menu` | Context menus, action lists | `DropdownMenuTrigger` + `DropdownMenuContent` |
| `Select` | Form selects with search | `onValueChange` |
| `Command` | Keyboard-driven search palette | `CommandInput` + `CommandList` |
| `Sheet` | Slide-in panel (sidebar drawer) | `side="left"` / `"right"` / `"bottom"` |
| `Collapsible` | Expandable content sections | `open` / `onOpenChange` |

### Display primitives
| Component | Use case |
|-----------|---------|
| `Card` | Content containers with header/body/footer |
| `Badge` | Status labels, tags, counts |
| `Alert` | Inline feedback (success, error, warning, info) |
| `Separator` | Visual dividers between sections |
| `Tooltip` | Hover labels on icons and truncated text |
| `Scroll Area` | Custom-styled overflow scroll containers |
| `Aspect Ratio` | Responsive media containers (16:9, 4:3, 1:1) |

### Form primitives
| Component | Notes |
|-----------|-------|
| `Input` | Base text input — compose with Label, FormMessage |
| `Tabs` | Tab navigation within a page section |

---

## 2. Page Layout Components

Higher-level compositions for app scaffolding.

### Navigation
```tsx
<SiteHeader>           // Top nav bar — logo + nav links + theme toggle
  <SidebarNav />       // Left sidebar — nested route links with active state
</SiteHeader>
<SiteFooter />         // Footer with links and copyright
```

### Content structure
```tsx
<PageHeader             // Section header inside a content area
  heading="Title"
  description="Subtitle text"
/>
<Pager                  // Prev/Next navigation for paginated content
  currentPage={page}
  totalPages={total}
/>
```

### Utility layout
```tsx
<Drawer />              // Full-height side panel (mobile nav, filters)
<ModeToggle />          // Light/dark/system theme switcher (uses next-themes)
```

---

## 3. Component Registry Pattern

Mage-UI uses a file-based registry so components can be added to any project via CLI without importing the full library.

### Registry structure
```
registry/
├── registry.json           // Component manifest (name, files, dependencies)
├── components/
│   ├── accordion.tsx
│   ├── dialog.tsx
│   └── ...
└── hooks/
    └── use-mobile.tsx
```

### registry.json entry shape
```json
{
  "name": "dialog",
  "type": "registry:ui",
  "files": ["components/dialog.tsx"],
  "dependencies": ["@radix-ui/react-dialog"],
  "devDependencies": [],
  "registryDependencies": ["button"]
}
```

### CLI add command (shadcn pattern)
```bash
npx shadcn@latest add dialog
```
Copies the source file into `src/components/ui/` — no hidden abstraction layer.

**Why registry over package:** Components are owned by the consuming project. Customize freely without forking a library or waiting for upstream PRs.

---

## 4. Utility Components

### CopyButton
```tsx
<CopyButton value={codeString} />  // Copies text to clipboard, shows check icon on success
```
Pattern: `useState(copied)` + `setTimeout` reset + `navigator.clipboard.writeText`.

### CommandMenu
```tsx
// Global keyboard palette (⌘K / Ctrl+K)
<CommandDialog open={open} onOpenChange={setOpen}>
  <CommandInput placeholder="Type a command..." />
  <CommandList>
    <CommandGroup heading="Navigation">
      <CommandItem onSelect={() => router.push('/dashboard')}>Dashboard</CommandItem>
    </CommandGroup>
  </CommandList>
</CommandDialog>
```
Wire up with `useEffect` listening for `keydown` `metaKey + k`.

### Callout
```tsx
<Callout type="warning" icon={AlertTriangle}>
  This action cannot be undone.
</Callout>
```
Variants: `default`, `warning`, `danger`. Composes Alert + Icon.

### CodeBlockWrapper
Wraps `<pre><code>` with syntax highlighting + CopyButton + optional line numbers. Use for documentation pages and AI response rendering.

---

## Anti-patterns

| ❌ Wrong | ✅ Correct |
|---|---|
| Importing entire UI library | Use registry pattern — copy only needed components |
| Custom modal from scratch | Compose Dialog + `useEffect` focus trap |
| Global state for theme | `next-themes` `ThemeProvider` at root |
| Inline `overflow: scroll` on content divs | Use ScrollArea for consistent cross-browser behavior |
| Hardcoded icon sizes | Pass `className="h-4 w-4"` as prop — composable |
