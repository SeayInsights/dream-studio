# TMDL Authoring Reference

Companion to `pbip-format.md`. Covers patterns and gotchas for writing correct TMDL content — the semantic model layer of a .pbip project.

Referenced by: client-work

---

## The `_measures` Table Pattern

Centralize all measures in a single table with no data rows. This is a best practice for maintainability.

In TMDL, create a table with no partitions and no columns — measures only:

```
table _Measures
	lineageTag: <leave existing, omit when creating new>

	measure 'Total Sales' = SUM(FactSales[SalesAmount])
		formatString: "$#,0.00;($#,0.00);$#,0.00"
		displayFolder: Revenue

	measure 'Sales QoQ %' = DIVIDE([Total Sales] - [Sales PQ], [Sales PQ])
		formatString: "0.0%"
		displayFolder: Revenue
```

Benefits:
- All business logic in one place — easy to find, audit, and document
- No calculated column clutter mixing with measures in the same table
- Cleanly separates storage (fact/dim tables) from calculation (measures table)

---

## Relationship Direction — Default to Single

Always default to single-direction cross-filtering. Only allow bi-directional when the model explicitly requires it, and document why.

**Why single-direction:**
- Bi-directional relationships can create ambiguous filter paths when multiple relationship chains exist
- They hide context transitions that are obvious in single-direction models
- They can cause performance issues on large models by expanding filter propagation unexpectedly

**When bi-directional is acceptable:**
- Many-to-many relationships that require it by design
- Bridge tables (role-playing dimensions)
- Always document with a `/// Reason: bi-directional required because...` annotation

**In TMDL:**
```
relationship FactSales-DimProduct
	fromTable: FactSales
	fromColumn: ProductKey
	toTable: DimProduct
	toColumn: ProductKey
	// crossFilteringBehavior: bothDirections  ← only add if required
```

---

## Calculation Groups

Calculation groups in TMDL use a `calculationGroup` block inside a table:

```
table 'Time Intelligence'
	calculationGroup
		precedence: 10

		calculationItem YTD = CALCULATE(SELECTEDMEASURE(), DATESYTD(DimDate[Date]))
			/// Year-to-date from Jan 1 to the last visible date

		calculationItem QTD = CALCULATE(SELECTEDMEASURE(), DATESQTD(DimDate[Date]))
			/// Quarter-to-date

		calculationItem MTD = CALCULATE(SELECTEDMEASURE(), DATESMTD(DimDate[Date]))
			/// Month-to-date

		calculationItem PY = CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR(DimDate[Date]))
			/// Prior year same period
```

**Gotcha:** Field parameters referencing a calculation group measure in Power BI resolve to ALL contained calculation items — not just the active one. If a field parameter appears to return multiple values, this is why.

---

## Field Parameter Gotcha

When a field parameter references a measure, it resolves to ALL measures contained in the parameter's value list — not just the currently selected one. This is by design but surprises most developers.

**Symptom:** A card visual showing a field parameter measure displays data that looks like a total of multiple measures.

**Fix:** The field parameter is working correctly — the visual's filter context is not set to a single item. Ensure the slicer driving the field parameter has single-select enabled and the visual is filtered accordingly.

---

## Three-Level Rename Chain

Every column in Power BI has three names that must all be tracked when renaming:

```
source_name (in the source database)
  → pq_name (the name after Power Query transformations)
    → pbi_name (the name visible in the model and DAX)
```

**When you rename a column in TMDL**, you are renaming `pbi_name`. You must also check:
1. `sourceColumn` property in the column definition (links to `pq_name`)
2. Any `Table.RenameColumns` steps in the M expression that produce `pq_name`
3. All DAX measures that reference `Table[ColumnName]` using `pbi_name`

**When you rename a Power Query step output**, you are changing `pq_name`. You must check:
1. The `sourceColumn` in TMDL that references this name
2. The `name` property of the column in TMDL

Never rename without tracing the full chain.

---

## Session Workflow

Safe TMDL editing workflow:
1. **Inspect first** — read the current TMDL before making any change
2. **Small changes** — edit one measure or one table at a time
3. **Validate immediately** — open the .pbip in Power BI Desktop after every edit; a parse error shows as a red warning in the field list
4. **Never batch** — don't queue 10 edits and validate once at the end; one bad tab character can corrupt the whole table block
5. **Python for file ops** — use Python with UTF-8 encoding when reading/writing TMDL; Windows shell tools break on accented characters
