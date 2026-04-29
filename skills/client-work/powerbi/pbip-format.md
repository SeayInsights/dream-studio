# Power BI Project Format (.pbip) Reference

## Folder structure

```
MyReport.pbip                        # entry point (JSON)
MyReport.Report/
  definition.pbir                    # report → semantic model link
  report.json                        # pages, visuals, layout — NEVER edit manually
  StaticResources/                   # images, custom visuals
MyReport.SemanticModel/
  definition.pbism                   # semantic model root
  definition/                        # TMDL folder (when TMDL enabled)
    database.tmdl
    tables/
      FactSales.tmdl
      DimDate.tmdl
    relationships.tmdl
    cultures/
      en-US.tmdl
```

## .pbip entry point

```json
{
  "version": "1.0",
  "artifacts": [{ "report": { "path": "MyReport.Report" } }],
  "settings": { "enableTmdlFormat": true }
}
```

## definition.pbir (report → semantic model link)

```json
{
  "version": "4.0",
  "datasetReference": {
    "byPath": { "path": "../MyReport.SemanticModel" }
  }
}
```

## TMDL — table with measure

```
table FactSales
  column SalesAmount
    dataType: double
    sourceColumn: SalesAmount
    formatString: "$#,0.00;($#,0.00);$#,0.00"

  measure 'Total Sales' = SUM(FactSales[SalesAmount])
    formatString: "$#,0.00;($#,0.00);$#,0.00"
    displayFolder: Revenue

  partition FactSales-partition
    mode: import
    source
      type: m
      expression:
        let
          Source = Sql.Database("server", "db"),
          Nav = Source{[Schema="dbo",Item="FactSales"]}[Data]
        in
          Nav
```

## TMDL — relationships

```
relationship FactSales-DimDate
  fromTable: FactSales
  fromColumn: DateKey
  toTable: DimDate
  toColumn: DateKey
```

## TMDL — RLS role

```
role 'Region Managers'
  tablePermissions
    table FactSales
      filterExpression: [RegionCode] = USERPRINCIPALNAME()
```

## Editing rules

- Validate JSON is well-formed in `.pbip`, `.pbir`, `.pbism` before saving
- TMDL is whitespace-sensitive — indent with 2 spaces, never tabs
- Measure expressions: single-line `= EXPRESSION` or multiline — expression on next line, indented 2 more spaces
- Never edit `report.json` manually — Power BI generates and owns this file
- After any TMDL edit, open in Power BI Desktop to validate before pushing
