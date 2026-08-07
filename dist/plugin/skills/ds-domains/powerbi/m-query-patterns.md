# BI Domain — M Query Patterns

Domain knowledge for Power Query / M-Query authoring and troubleshooting.
Referenced by: client-work

---

## Query Folding

- **Always check** the query folding indicator (green = folded, yellow = partial, red = broken)
- Folding keeps transformations at the source — critical for large datasets
- **Common fold-breakers**: `Table.Buffer`, `List.Generate`, custom functions, row-level error replacement
- When folding breaks, document the step that breaks it with an inline comment:
  ```m
  // Folding breaks here: List.Accumulate not supported by this connector
  ```

---

## Patterns

### Dynamic data sources
Use parameter tables for connection strings and config values — never hardcode server names or URLs in queries.

### Error handling
```m
= Table.ReplaceErrorValues(Source, {{"ColumnName", null}})
// or with try...otherwise for per-cell handling:
= Table.TransformColumns(Source, {{"ColumnName", each try _ otherwise null}})
```

### Parameterized queries
```m
let
    Source = Sql.Database(ServerParam, DatabaseParam),
    Query = Value.NativeQuery(Source, "SELECT * FROM " & TableParam & " WHERE date >= " & DateParam)
in Query
```

### Splitting complex queries
- One query per logical entity — don't chain 20 steps in a single query
- Use `let...in` blocks with named intermediate steps for readability
- Reference shared steps as named queries (Enable Load = false) to avoid duplication

---

## M Query Error Reference

| Error | Fix |
|---|---|
| `DataFormat.Error: Invalid cell value '#N/A'` | `Table.ReplaceErrorValues(Source, {{"Column", null}})` |
| Query folding broken (yellow indicator) | Find the step that breaks folding; add inline comment; document in handoff |
| `Expression.Error: Column X not found` | Column renamed in source — update `Table.RenameColumns` step |
| Refresh credential error | Re-enter credentials in Data Source Settings; check gateway status |
| `Formula.Firewall: Query X accesses data sources with privacy levels` | Set privacy level for each source in Options → Privacy |
| `OLE DB or ODBC error: Timeout expired` | Query too heavy for source; push filters earlier in the chain; add folding |
| `DataSource.Error: Connection refused` | Gateway offline or wrong gateway assigned; check Power BI service data source settings |

---

## Semantic Model Validation

When a semantic model fails to open or refresh:
1. Open in Power BI Desktop → trigger Refresh → read full error in refresh pane
2. Check column data types match expected (`Date` vs `DateTime` vs `Text` are common mismatches)
3. Relationships: verify join columns have identical data types on both sides
4. TMDL syntax errors: read file line by line — indentation and keyword spelling are exact
5. After TMDL edits: open Desktop, check field list for red indicators before publishing
