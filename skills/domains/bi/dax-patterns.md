# BI Domain — DAX Patterns

Domain knowledge for Power BI semantic modeling and DAX authoring.
Referenced by: client-work

---

## Data Modeling

- **Star schema**: fact tables + dimension tables, no wide flat tables
- **Naming**: `dim_[entity]`, `fact_[process]`, `bridge_[relationship]`
- **Date table**: always create a dedicated date dimension — never use auto date/time
- **Relationships**: avoid bi-directional unless the model explicitly requires it; document why when used

---

## DAX Patterns

### Measures
- Always use `VAR` for multi-step measures — never nest `CALCULATE` without reason
- Standard pattern:
  ```dax
  Measure Name =
  VAR result = CALCULATE(SUM(Table[Column]), Filter)
  RETURN result
  ```

### Time Intelligence
- Use `DATEADD`, `SAMEPERIODLASTYEAR` with the dedicated date table (never with auto date/time)
- MTD/QTD/YTD: use `TOTALMTD`, `TOTALQTD`, `TOTALYTD` — pass the date column from the date dimension
- Rolling periods: `DATESINPERIOD` with negative interval

### Row-Level Security
- Implement per client requirement: `USERPRINCIPALNAME()` against a security table
- Test with `Modeling → View As Role` for every defined role
- Document the security table structure and expected behavior in the handoff doc

### Context Issues
- Implicit context transition in calculated columns: always explicit `CALCULATE([Measure])`
- Filter propagation: use `TREATAS` when joining tables without a physical relationship
- `ALL` vs `ALLEXCEPT`: `ALL` removes all filters from a table; `ALLEXCEPT` removes all except named columns

---

## DAX Error Reference

| Error | Likely cause | Fix |
|---|---|---|
| "A function has been used in a True/False expression" | Filter arg is not boolean | `CALCULATE([M], Table[Col] = "x")` |
| "Circular dependency detected" | Measure references itself through chain | Trace the chain; use `VAR` to break the loop |
| "The column X does not exist" | Wrong table prefix or renamed column | Verify exact name in field list |
| "EARLIER cannot be used" | EARLIER outside row context | Replace with `VAR prev = [value]` pattern |
| Wrong totals / context issues | Implicit context transition | Wrap with explicit `CALCULATE([Measure])` |
| "Cannot convert value 'X' to type Integer" | Data type mismatch at join | Check both sides of relationship for identical types |
