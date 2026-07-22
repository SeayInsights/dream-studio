"""SARIF file upload/import endpoint.

WO-GF-API-ROUTES: split out of security.py.
"""

from __future__ import annotations

import tempfile
from typing import Any

from fastapi import File, HTTPException, UploadFile

from projections.parsers.sarif_parser import parse_sarif_file

from .security_router import router


@router.post("/security/sarif/import")
async def import_sarif_file(
    file: UploadFile = File(..., description="SARIF file to import")
) -> dict[str, Any]:
    """
    Upload SARIF file for parsing and import.

    Accepts multipart/form-data file upload, saves to temp location,
    and calls parse_sarif_file() to process the results.

    Returns {imported: count, skipped: count, errors: []}
    """
    # Validate file extension
    if not file.filename or (
        not file.filename.endswith(".sarif") and not file.filename.endswith(".json")
    ):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Expected .sarif or .json file."
        )

    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".sarif", delete=False) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        imported = parse_sarif_file(tmp_path)
        result = {"imported": imported, "skipped": 0, "errors": []}

        # Clean up temp file
        import os

        os.unlink(tmp_path)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
