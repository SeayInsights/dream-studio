# Power BI Project Format (.pbip) Reference

## Folder Structure

```
MyReport.pbip                              # entry point (JSON)
MyReport.Report/
  definition.pbir                          # report → semantic model link
  report.json                              # pages, visuals, layout — NEVER edit manually
  StaticResources/                         # images, custom visuals
MyReport.SemanticModel/
  definition.pbism                         # semantic model root
  definition/                              # TMDL folder (when TMDL enabled)
    database.tmdl
    tables/
      FactSales.tmdl
      DimDate.tmdl
    relationships.tmdl
    expressions.tmdl                       # shared M expressions / parameters
    roles/                                 # RLS role files (one per role)
      Region Managers.tmdl
    cultures/
      en-US.tmdl
    diagramLayout.json                     # diagram layout — NEVER edit manually
```

## .pbip Entry Point

```json
{
  "version": "1.0",
  "artifacts": [{ "report": { "path": "MyReport.Report" } }],
  "settings": { "enableTmdlFormat": true }
}
```

## definition.pbir (Report → Semantic Model Link)

```json
{
  "version": "4.0",
  "datasetReference": {
    "byPath": { "path": "../MyReport.SemanticModel" }
  }
}
```

## TMDL Syntax Rules

**Indentation — most critical rule:**
- Indent with tabs, never spaces — spaces cause parse errors in Power BI Desktop

**Object descriptions:**
- Descriptions go ABOVE the object as `/// Description text`, NOT as a `description:` property inside the object body
- Correct: `/// Total revenue from all sales channels` then `measure 'Total Sales' = ...`
- Wrong: `measure 'Total Sales' = ...` then `    description: "Total revenue..."`

**Measure placement:**
- Measures go ABOVE column declarations within a table block
- Wrong order: columns first, then measures

**Measure format:**
- Single-line: `measure 'Name' = EXPRESSION`
- Multi-line: measure name on one line, expression on the next line indented with an extra tab; wrap complex expressions in backtick fences

**lineageTag:**
- Never add `lineageTag` when creating new objects — Power BI Desktop generates these automatically
- Only preserve existing lineageTags when editing — never invent values

**Comments:**
- `//` comments are NOT valid in TMDL body — only valid inside M expression blocks
- To document a measure, use the `/// Description` annotation above it

**Names with special characters:**
- Names with spaces or special characters must be single-quoted: `'My Measure Name'`
- Simple names (no spaces, no special chars) do not need quotes: `SalesAmount`

## TMDL — Table with Measure

```
table FactSales
	/// Total revenue from all sales channels
	measure 'Total Sales' = SUM(FactSales[SalesAmount])
		formatString: "$#,0.00;($#,0.00);$#,0.00"
		displayFolder: Revenue

	column SalesAmount
		dataType: double
		sourceColumn: SalesAmount
		formatString: "$#,0.00;($#,0.00);$#,0.00"

	partition FactSales-partition
		mode: import
		source
			type: m
			expression:
				let
					// Comments are valid inside M expression blocks
					Source = Sql.Database("server", "db"),
					Nav = Source{[Schema="dbo",Item="FactSales"]}[Data]
				in
					Nav
```

## TMDL — Relationships

```
relationship FactSales-DimDate
	fromTable: FactSales
	fromColumn: DateKey
	toTable: DimDate
	toColumn: DateKey
```

## TMDL — RLS Role

```
role 'Region Managers'
	tablePermissions
		table FactSales
			filterExpression: [RegionCode] = USERPRINCIPALNAME()
```

## M-Query Conventions

- Step names use past-tense verbs: `Source`, `FilteredRows`, `RenamedColumns`, `TypeChanged`
- Step names: max 50 characters
- `//` comments ARE valid inside M expression blocks (unlike TMDL body)
- Use descriptive step names — avoid `Custom1`, `Added Column`, and other default Power Query generated names

## PBIP Detection

- Never hardcode `.SemanticModel` in scripts or searches — projects use named folders like `Sales.SemanticModel` or `KrogerDashboard.SemanticModel`
- Detect dynamically using a `*.SemanticModel` glob pattern
- Store the detected path as `PBIP_DIR` and reuse it throughout the script — do not re-detect per operation

## Rename Safety Checklist

When renaming ANY measure, column, table, or field, check all 8 scopes:

1. TMDL table files (`definition/tables/*.tmdl`)
2. `relationships.tmdl`
3. PBIR visual JSON (`MyReport.Report/definition/pages/*/visuals/*/visual.json`)
4. Report filter definitions
5. Sort-by-column definitions
6. Report extensions and visual calculations
7. DAX query files (`.dax`)
8. `diagramLayout.json`

## File Operations

- Use Python with UTF-8 encoding for all file reads and writes on TMDL and M-query files
- Windows shell `grep` (and `findstr`) break on accented characters (é, è, ê, ü) common in French and German Power BI deployments
- Python example: `open(path, encoding='utf-8')`

## Editing Rules

- Validate JSON is well-formed in `.pbip`, `.pbir`, `.pbism` before saving
- Never edit `report.json` or `diagramLayout.json` manually — Power BI Desktop generates and owns these files
- After any TMDL edit, open in Power BI Desktop to validate before pushing
