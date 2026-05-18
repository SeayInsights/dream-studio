---
source: https://github.com/shadcn-ui/ui
extracted: 2026-05-02
pattern: component-composition
purpose: React component composition rules with correct/incorrect examples
---

# Component Composition Patterns

Component composition patterns from shadcn-ui showing correct structures and common mistakes to avoid. These patterns help LLMs and developers build components with the right hierarchy and avoid invalid nesting.

## 1. Card Components

### Correct Structure

```tsx
<Card>
  <CardHeader>
    <CardTitle>Card Title</CardTitle>
    <CardDescription>Card Description</CardDescription>
    <CardAction>Card Action</CardAction>
  </CardHeader>
  <CardContent>
    <p>Card Content</p>
  </CardContent>
  <CardFooter>
    <p>Card Footer</p>
  </CardFooter>
</Card>
```

### Composition Tree

```text
Card
├── CardHeader
│   ├── CardTitle
│   ├── CardDescription
│   └── CardAction
├── CardContent
└── CardFooter
```

### Notes
- `CardAction` places content in the top-right of the header (buttons, badges)
- All sections are optional but order matters
- Small cards use `size="sm"` prop for tighter spacing

---

## 2. Dialog Components

### Correct Structure

```tsx
<Dialog>
  <DialogTrigger>Open</DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Are you absolutely sure?</DialogTitle>
      <DialogDescription>
        This action cannot be undone.
      </DialogDescription>
    </DialogHeader>
    <DialogFooter>
      <Button>Action</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### Composition Tree

```text
Dialog
├── DialogTrigger
└── DialogContent
    ├── DialogHeader
    │   ├── DialogTitle
    │   └── DialogDescription
    └── DialogFooter
```

---

## 3. Alert Dialog

### Correct Structure

```tsx
<AlertDialog>
  <AlertDialogTrigger render={<Button variant="outline" />}>
    Show Dialog
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogMedia />
      <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
      <AlertDialogDescription>
        This action cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction>Continue</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

### Composition Tree

```text
AlertDialog
├── AlertDialogTrigger
└── AlertDialogContent
    ├── AlertDialogHeader
    │   ├── AlertDialogMedia
    │   ├── AlertDialogTitle
    │   └── AlertDialogDescription
    └── AlertDialogFooter
        ├── AlertDialogCancel
        └── AlertDialogAction
```

### Notes
- Footer should have both Cancel and Action buttons
- `AlertDialogMedia` is optional for icons/images

---

## 4. Button Groups

### Correct Structure

```tsx
<ButtonGroup>
  <Button>Button 1</Button>
  <ButtonGroupSeparator />
  <Button>Button 2</Button>
</ButtonGroup>
```

### Composition Tree

```text
ButtonGroup
├── Button or Input
├── ButtonGroupSeparator
└── ButtonGroupText
```

### Notes
- Buttons with `variant="outline"` don't need separators (they have borders)
- For other variants, separators improve visual hierarchy
- Can nest ButtonGroups to create complex layouts with spacing

### Incorrect Pattern

```tsx
// WRONG: ButtonGroup vs ToggleGroup confusion
<ButtonGroup>
  <Button toggled={true}>Toggle Me</Button>
</ButtonGroup>
```

### Correct Alternative

```tsx
// Use ToggleGroup for state toggling
<ToggleGroup>
  <ToggleItem value="option1">Option 1</ToggleItem>
  <ToggleItem value="option2">Option 2</ToggleItem>
</ToggleGroup>
```

---

## 5. Input Groups

### Correct Structure

```tsx
<InputGroup>
  <InputGroupInput placeholder="Search..." />
  <InputGroupAddon align="inline-end">
    <SearchIcon />
  </InputGroupAddon>
</InputGroup>
```

### Composition Tree

```text
InputGroup
├── InputGroupInput or InputGroupTextarea
├── InputGroupAddon
├── InputGroupButton
└── InputGroupText
```

### Important Rules
- **For focus management**: `InputGroupAddon` must be placed AFTER the input in DOM
- Use `align` prop to visually position the addon
- For `InputGroupInput`: use `inline-start` or `inline-end` alignment
- For `InputGroupTextarea`: use `block-start` or `block-end` alignment
- Custom inputs need `data-slot="input-group-control"` attribute for focus handling

### Addon Alignment

```tsx
// Addon at start (visually)
<InputGroup>
  <InputGroupInput />
  <InputGroupAddon align="inline-start">
    <SearchIcon />
  </InputGroupAddon>
</InputGroup>

// Addon at end
<InputGroup>
  <InputGroupInput />
  <InputGroupAddon align="inline-end">
    <SearchIcon />
  </InputGroupAddon>
</InputGroup>
```

---

## 6. Select Components

### Correct Structure

```tsx
const items = [
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" }
]

<Select items={items}>
  <SelectTrigger className="w-[180px]">
    <SelectValue placeholder="Theme" />
  </SelectTrigger>
  <SelectContent>
    <SelectGroup>
      <SelectLabel>Theme</SelectLabel>
      {items.map((item) => (
        <SelectItem key={item.value} value={item.value}>
          {item.label}
        </SelectItem>
      ))}
    </SelectGroup>
  </SelectContent>
</Select>
```

### Composition Tree

```text
Select
├── SelectTrigger
│   └── SelectValue
└── SelectContent
    ├── SelectGroup
    │   ├── SelectLabel
    │   ├── SelectItem
    │   └── SelectItem
    ├── SelectSeparator
    └── SelectGroup
        ├── SelectLabel
        ├── SelectItem
        └── SelectItem
```

---

## 7. Tabs

### Correct Structure

```tsx
<Tabs defaultValue="account" className="w-[400px]">
  <TabsList>
    <TabsTrigger value="account">Account</TabsTrigger>
    <TabsTrigger value="password">Password</TabsTrigger>
  </TabsList>
  <TabsContent value="account">Account content</TabsContent>
  <TabsContent value="password">Password content</TabsContent>
</Tabs>
```

### Composition Tree

```text
Tabs
├── TabsList
│   ├── TabsTrigger
│   └── TabsTrigger
├── TabsContent
└── TabsContent
```

---

## 8. Accordion

### Correct Structure

```tsx
<Accordion defaultValue={["item-1"]}>
  <AccordionItem value="item-1">
    <AccordionTrigger>Is it accessible?</AccordionTrigger>
    <AccordionContent>
      Yes. It adheres to the WAI-ARIA design pattern.
    </AccordionContent>
  </AccordionItem>
  <AccordionItem value="item-2">
    <AccordionTrigger>Is it styled?</AccordionTrigger>
    <AccordionContent>
      Yes. It comes with default styles.
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

### Composition Tree

```text
Accordion
├── AccordionItem
│   ├── AccordionTrigger
│   └── AccordionContent
└── AccordionItem
    ├── AccordionTrigger
    └── AccordionContent
```

### Notes
- Use `multiple` prop to allow multiple items open simultaneously
- Each `AccordionItem` can be individually disabled

---

## 9. Dropdown Menu

### Correct Structure

```tsx
<DropdownMenu>
  <DropdownMenuTrigger render={<Button variant="outline" />}>
    Open
  </DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuGroup>
      <DropdownMenuLabel>My Account</DropdownMenuLabel>
      <DropdownMenuItem>Profile</DropdownMenuItem>
      <DropdownMenuItem>Billing</DropdownMenuItem>
    </DropdownMenuGroup>
    <DropdownMenuSeparator />
    <DropdownMenuGroup>
      <DropdownMenuItem>Team</DropdownMenuItem>
    </DropdownMenuGroup>
  </DropdownMenuContent>
</DropdownMenu>
```

### Composition Tree (Full)

```text
DropdownMenu
├── DropdownMenuTrigger
└── DropdownMenuContent
    ├── DropdownMenuGroup
    │   ├── DropdownMenuLabel
    │   ├── DropdownMenuItem
    │   └── DropdownMenuItem
    ├── DropdownMenuSeparator
    ├── DropdownMenuGroup
    │   ├── DropdownMenuLabel
    │   ├── DropdownMenuCheckboxItem
    │   └── DropdownMenuCheckboxItem
    ├── DropdownMenuSeparator
    ├── DropdownMenuGroup
    │   ├── DropdownMenuLabel
    │   └── DropdownMenuRadioGroup
    │       ├── DropdownMenuRadioItem
    │       └── DropdownMenuRadioItem
    └── DropdownMenuSub
        ├── DropdownMenuSubTrigger
        └── DropdownMenuSubContent
            └── DropdownMenuGroup
                ├── DropdownMenuLabel
                ├── DropdownMenuItem
                └── DropdownMenuItem
```

### Notes
- `DropdownMenuSub` creates nested submenus
- `DropdownMenuShortcut` shows keyboard hints
- Combine with icons for better scanning

---

## 10. Popover

### Correct Structure

```tsx
<Popover>
  <PopoverTrigger render={<Button variant="outline" />}>
    Open Popover
  </PopoverTrigger>
  <PopoverContent>
    <PopoverHeader>
      <PopoverTitle>Title</PopoverTitle>
      <PopoverDescription>Description text here.</PopoverDescription>
    </PopoverHeader>
  </PopoverContent>
</Popover>
```

### Composition Tree

```text
Popover
├── PopoverTrigger
└── PopoverContent
    └── PopoverHeader (optional)
        ├── PopoverTitle
        └── PopoverDescription
```

---

## 11. Breadcrumb

### Correct Structure

```tsx
<Breadcrumb>
  <BreadcrumbList>
    <BreadcrumbItem>
      <BreadcrumbLink render={<a href="/" />}>Home</BreadcrumbLink>
    </BreadcrumbItem>
    <BreadcrumbSeparator />
    <BreadcrumbItem>
      <BreadcrumbLink render={<a href="/components" />}>
        Components
      </BreadcrumbLink>
    </BreadcrumbItem>
    <BreadcrumbSeparator />
    <BreadcrumbItem>
      <BreadcrumbPage>Breadcrumb</BreadcrumbPage>
    </BreadcrumbItem>
  </BreadcrumbList>
</Breadcrumb>
```

### Composition Tree

```text
Breadcrumb
└── BreadcrumbList
    ├── BreadcrumbItem
    │   └── BreadcrumbLink
    ├── BreadcrumbSeparator
    ├── BreadcrumbItem
    │   └── BreadcrumbLink
    ├── BreadcrumbSeparator
    └── BreadcrumbItem
        └── BreadcrumbPage
```

### Notes
- Last item uses `BreadcrumbPage` (not clickable)
- Can compose `BreadcrumbItem` with `DropdownMenu` for collapsed breadcrumbs

---

## 12. Field / Form Components

### Correct Structure - Single Field

```tsx
<Field>
  <FieldLabel htmlFor="name">Full name</FieldLabel>
  <Input id="name" autoComplete="off" placeholder="Evil Rabbit" />
  <FieldDescription>This appears on invoices and emails.</FieldDescription>
  <FieldError>Please enter a valid name.</FieldError>
</Field>
```

### Composition Tree - Field

```text
Field
├── FieldLabel
├── Input / Textarea / Switch / Select
├── FieldDescription
└── FieldError
```

### Correct Structure - Field Group

```tsx
<FieldSet>
  <FieldLegend>Profile</FieldLegend>
  <FieldDescription>This appears on invoices and emails.</FieldDescription>
  <FieldGroup>
    <Field>
      <FieldLabel htmlFor="name">Full name</FieldLabel>
      <Input id="name" />
    </Field>
    <FieldSeparator />
    <Field>
      <FieldLabel htmlFor="username">Username</FieldLabel>
      <Input id="username" aria-invalid />
      <FieldError>Choose another username.</FieldError>
    </Field>
  </FieldGroup>
</FieldSet>
```

### Composition Tree - FieldGroup

```text
FieldGroup
├── Field
│   ├── FieldLabel
│   ├── Input / Textarea / Switch / Select
│   ├── FieldDescription
│   └── FieldError
├── FieldSeparator
└── Field
    ├── FieldLabel
    └── Input / Textarea / Switch / Select
```

### Notes
- Use `FieldSet` for grouping related fields
- `FieldSeparator` divides sections within a group
- For horizontal fields (like switches), use `orientation="horizontal"` on Field

---

## 13. Button with Icons

### Correct Structure

```tsx
// Icon at start
<Button>
  <Icon data-icon="inline-start" />
  Click Me
</Button>

// Icon at end
<Button>
  Click Me
  <Icon data-icon="inline-end" />
</Button>

// Icon only
<Button size="icon" aria-label="Settings">
  <SettingsIcon />
</Button>
```

### Important Rules
- **Always add `data-icon="inline-start"` or `data-icon="inline-end"`** for correct spacing
- Use `size="icon"` for icon-only buttons
- Icon-only buttons MUST have `aria-label` for accessibility

### Incorrect Pattern

```tsx
// WRONG: Missing data-icon attribute
<Button>
  <Icon />
  Click Me
</Button>

// WRONG: Using Button with render for links
<Button render={<a href="/about" />} nativeButton={false}>
  About
</Button>
```

### Correct Alternative

```tsx
// Use buttonVariants helper for links
import { buttonVariants } from "@/components/ui/button"

<a href="/about" className={buttonVariants({ variant: "outline" })}>
  About
</a>
```

### Why
The Base UI `Button` component always applies `role="button"`, which overrides the semantic link role on `<a>` elements. Use `buttonVariants` with a plain `<a>` tag instead.

---

## 14. Button with Spinner

### Correct Structure

```tsx
<Button disabled>
  <Spinner data-icon="inline-start" />
  Loading...
</Button>
```

### Notes
- Spinner needs `data-icon="inline-start"` or `data-icon="inline-end"` for spacing
- Disable button during loading state

---

## Common Anti-Patterns

### 1. ButtonGroup vs ToggleGroup

**WRONG:**
```tsx
<ButtonGroup>
  <Button toggled={true}>Toggle Me</Button>
</ButtonGroup>
```

**CORRECT:**
- Use `ButtonGroup` for buttons that perform actions
- Use `ToggleGroup` for buttons that toggle state

### 2. Button as Link

**WRONG:**
```tsx
<Button render={<a href="/about" />} nativeButton={false}>
  About
</Button>
```

**CORRECT:**
```tsx
import { buttonVariants } from "@/components/ui/button"

<a href="/about" className={buttonVariants({ variant: "outline" })}>
  About
</a>
```

### 3. Missing Icon Attributes

**WRONG:**
```tsx
<Button>
  <Icon />
  Click Me
</Button>
```

**CORRECT:**
```tsx
<Button>
  <Icon data-icon="inline-start" />
  Click Me
</Button>
```

### 4. InputGroupAddon Placement

**WRONG:**
```tsx
// Addon before input breaks focus management
<InputGroup>
  <InputGroupAddon align="inline-start">
    <SearchIcon />
  </InputGroupAddon>
  <InputGroupInput />
</InputGroup>
```

**CORRECT:**
```tsx
// Addon after input, use align to position visually
<InputGroup>
  <InputGroupInput />
  <InputGroupAddon align="inline-start">
    <SearchIcon />
  </InputGroupAddon>
</InputGroup>
```

### 5. Invalid Select State

**WRONG:**
```tsx
<SelectTrigger data-invalid>
  <SelectValue />
</SelectTrigger>
```

**CORRECT:**
```tsx
// Invalid state goes on Field wrapper AND aria-invalid on trigger
<Field data-invalid>
  <FieldLabel>Fruit</FieldLabel>
  <SelectTrigger aria-invalid>
    <SelectValue />
  </SelectTrigger>
</Field>
```

---

## React/TypeScript Specific Guidance

### Type Safety

```tsx
// Define items array with proper typing
const items: { label: string; value: string }[] = [
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" }
]

<Select items={items}>
  {/* ... */}
</Select>
```

### Render Props

Many components use `render` prop for custom elements:

```tsx
<DialogTrigger render={<Button variant="outline" />}>
  Open Dialog
</DialogTrigger>

<BreadcrumbLink render={<a href="/" />}>
  Home
</BreadcrumbLink>
```

### AsChild Pattern

Some components support `asChild` to merge props with child:

```tsx
<ButtonGroupText asChild>
  <Label htmlFor="name">Text</Label>
</ButtonGroupText>
```

---

## Accessibility Notes

1. **ARIA Labels**: Icon-only buttons need `aria-label`
2. **Invalid States**: Use both `data-invalid` on wrapper and `aria-invalid` on control
3. **Focus Management**: InputGroup addon placement affects tab order
4. **Semantic HTML**: Use proper link elements with `buttonVariants` instead of Button component
5. **Button Groups**: Set `aria-label` or `aria-labelledby` on ButtonGroup
6. **Disabled States**: Always disable buttons during loading

---

## CLI Integration

Pull component documentation including composition patterns into context:

```bash
npx shadcn@latest docs card
npx shadcn@latest docs button-group
npx shadcn@latest docs select
```

This is automatically done when using shadcn/skills MCP server.
