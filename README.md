# Regulated Document Builder Demo

PDF forms often need the same approval metadata, barcode, and watermark applied repeatedly. This demo shows a small batch-oriented document builder for that workflow.

## Features

- Inserts text, barcode, and watermark layers into existing PDF pages
- Supports single-file runs and JSON batch input
- Keeps layout coordinates, fonts, and resources in configuration
- Provides optional database update and file handoff hooks behind environment flags
- Includes unit tests around configuration, PDF output, and update behavior

## Stack

- Python 3.12
- PyMuPDF, Pillow
- python-barcode
- pyodbc, paramiko
- pytest

## Run

```bash
uv sync --dev
uv run run.py "samples/input.pdf" "REQ-001" "BARCODE-001" "0" "LOT-001" "Requester" "Approver" "QC" "2026-01-01" "1" "" "Y" "0" "0"
```

Batch input is also supported:

```bash
uv run run.py --json "samples/jobs.json"
```

## Configuration

The checked-in defaults use local demo paths. Real deployment values should be provided through `.env` or runtime environment variables.

- `ASSET_FONT_MALGUN`, `ASSET_FONT_MALGUN_BOLD`, `ASSET_FONT_BARCODE`
- `WATERMARK_IMAGE_PATH`
- `DB_UPDATE_ENABLED`, `DB_SERVER`, `DB_NAME`
- `SECURE_FILE_ENABLED`, `SSH_HOSTNAME`, `SSH_USERNAME`
- `STORAGE_COMPLETED_PATH`

No private certificates, internal network paths, production documents, or bundled Windows installers are included.

## Test

```bash
uv run pytest
```