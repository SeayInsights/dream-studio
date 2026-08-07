# Verify Skill — Simple Example Output

## Verification Report

### Test 1: Button renders with label ✅
**Method:** Rendered in test app
**Input:** `<Button label="Click me" onClick={() => {}} />`
**Expected:** Button displays "Click me"
**Actual:** ✅ Button displays "Click me"
**Evidence:** Screenshot saved to `.verification/button-render.png`

### Test 2: onClick handler fires ✅
**Method:** Click event test
**Input:** Clicked button in test app
**Expected:** Handler called
**Actual:** ✅ Console logged "Button clicked"
**Evidence:** Console log in `.verification/button-click.log`

### Test 3: Accessibility ✅
**Method:** axe-core scan
**Input:** Button component
**Expected:** No accessibility violations
**Actual:** ✅ No violations found
**Evidence:** Report in `.verification/axe-report.json`

### Regression Check ✅
**Checked:** Other components still render
**Result:** ✅ No regressions detected

## Summary
✅ Verification PASS — all tests passed
📁 Evidence: `.verification/` directory
