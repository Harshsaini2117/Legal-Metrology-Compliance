# SIH26034 - Legal Metrology AI Compliance Inspection

## Executive summary

SIH26034 is a local web application for screening packaged-commodity labels against selected Legal Metrology declaration checks. A user uploads one label image; the system preprocesses it, extracts English OCR text with coordinates, uses spatially aware extraction to form structured declarations, evaluates deterministic rules, preserves linked evidence, generates a PDF report, and stores a local scan history. It is an explainable screening tool: OCR supplies observations, while deterministic rules determine the reported compliance outcome.

## Problem statement

Packaged commodities must display required declarations such as the product name, net quantity, MRP, manufacturer/packer/importer details, date information, and consumer-care information. Manual label review is slow and can be difficult to audit. Raw OCR alone is not sufficient because a text string does not establish which declaration it represents, whether it is applicable, or whether it satisfies a rule.

## Proposed solution

The application converts a package-label image into structured declarations and evaluates a fixed set of evidence-aware Legal Metrology checks. It returns the assessment, linked OCR evidence, an annotated evidence image, and a generated PDF report. Uncertain or missing evidence is surfaced as `UNABLE_TO_VERIFY` rather than being silently treated as compliant or as a confirmed violation.

## Why this is more than OCR

**OCR alone does not determine compliance.** This system combines OCR text and bounding boxes with spatial analysis, structured-field extraction, applicability context, and deterministic legal rules. The result is an explainable check outcome with the OCR evidence used to support it, rather than an unstructured text dump.

## End-to-end workflow

```text
Image
  -> Preprocessing
  -> PaddleOCR (text, confidence, bounding boxes)
  -> Spatial Analysis
  -> Field Extraction + applicability context
  -> Deterministic Compliance Rules
  -> Linked OCR Evidence + annotated evidence image
  -> PDF Report + local scan history
```

## System architecture

```text
+--------------------------------------------------------------+
| Frontend: HTML / CSS / vanilla JavaScript                    |
| image preview | processing state | result | evidence | history|
+------------------------------+-------------------------------+
                               | HTTP (localhost)
+------------------------------v-------------------------------+
| FastAPI backend                                              |
| POST /scan                                                   |
| validation -> preprocessing -> OCR -> extraction             |
| -> rules -> evidence -> report -> persistence                |
+---------+------------------+------------------+--------------+
          |                  |                  |
          v                  v                  v
   OpenCV + Pillow       PaddleOCR          ReportLab PDF
   image processing      English OCR         report generation
          |
          v
 data/raw | data/processed | data/evidence | data/reports | SQLite
```

## Implemented features

- Single-image upload for JPEG, PNG, and WEBP files up to 10 MB.
- Image preview before scan submission.
- EXIF-orientation handling, proportional resizing, and LAB luminance normalization.
- PaddleOCR-based English text extraction with confidence values and bounding boxes.
- OCR retry logic for low-quality results and selected small-text declaration evidence.
- Spatially aware declaration extraction and field-evidence mapping.
- Deterministic, evidence-aware compliance checks with applicability context.
- OCR evidence linked to fields/checks and an annotated evidence image.
- PDF report generation for completed scans.
- Local SQLite-backed recent-scan history and report download links.
- Responsive frontend layouts for desktop and smaller widths.

## Compliance checks currently implemented

| Rule ID | Declaration checked | Condition |
| --- | --- | --- |
| LMPC-R6-01 | Common or generic product name | Required declaration check |
| LMPC-R6-02 | Manufacturer, packer, or importer identification and address | Required declaration check |
| LMPC-R6-03 | Country of origin | Conditional for imported products |
| LMPC-R6-04 | Net quantity | Required declaration check |
| LMPC-R6-05 | Maximum Retail Price (MRP) | Required declaration check |
| LMPC-R6-06 | MRP inclusive-of-taxes wording | Required declaration check |
| LMPC-R6-07 | Manufacture, packing, or import month/year | Required declaration check |
| LMPC-R6-08 | Consumer-care details | Requires a usable phone number or email |
| LMPC-R6-09 | Unit sale price | Conditional where applicable |
| LMPC-R6-10 | Relevant size or dimensions | Conditional where relevant |

The rule engine works with normalized text fields and explicit applicability context. It does not infer visual placement, font size, label completeness, or category-specific exemptions.

## Assessment semantics

| Outcome | Meaning |
| --- | --- |
| `PASS` | Applicable check was verified from usable evidence. |
| `FAIL` | An applicable declaration was detected but is invalid, or an established required declaration is absent. |
| `NOT_APPLICABLE` | The system has evidence that a conditional declaration is not required for the current context. |
| `UNABLE_TO_VERIFY` | Available OCR/context is insufficient to safely decide the requirement. This sets `review_required`; it is not a confirmed violation. |

The overall result is `NON_COMPLIANT` when a confirmed failure exists, `UNABLE_TO_VERIFY` when no failure exists but at least one check is unresolved, `COMPLIANT` when all applicable checks pass, and `NOT_APPLICABLE` if no applicable checks can be evaluated.

## Explainable evidence

Each OCR detection can include:

- recognized text;
- OCR confidence;
- a polygon bounding box;
- a related extracted field and, when uniquely determinable, a related rule.

The backend also maps field evidence to compliance checks. An evidence renderer writes an annotated copy of the source label: ordinary OCR detections are outlined in blue and evidence associated with failed checks is outlined in red. OCR coordinates from a resized preprocessed image are scaled back to the original image before rendering.

## Compliance scoring and evidence coverage

Two distinct metrics are produced by the rules engine:

- **Verified compliance score**: `PASS / verified checks * 100`. It describes outcomes only among checks that were verified.
- **Evidence coverage**: `verified checks / (verified checks + unable-to-verify checks) * 100`.

`NOT_APPLICABLE` checks are excluded from these denominators. The frontend presents evidence coverage so a high verified-check score is not mistaken for complete evidence coverage.

## PDF report generation

For a completed scan, the backend attempts to create a PDF in `data/reports/`. The report includes the scan summary, extracted fields, compliance checks, violations, and an OCR-evidence summary. A generated report is available at the scan-specific report endpoint; report-generation failure is returned as a scan field without discarding the completed scan result.

## Frontend demo workflow

1. Open the local frontend and choose a valid package-label image.
2. Confirm the image preview and select **Run Inspection**.
3. Review the non-simulated processing state while the backend returns one completed response.
4. Review overall status, evidence coverage, extracted declarations, rule outcomes, and linked OCR evidence.
5. Use **View report** to open/download the generated PDF.
6. Refresh **Recent inspections** to view the persisted local history.

## API

The current FastAPI application exposes the following endpoints.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Returns local service status and project identity. |
| `POST` | `/scan/upload` | Validates and stores a supported image without running the full pipeline. |
| `POST` | `/scan` | Validates, stores, processes, reports on, and persists one product image. |
| `GET` | `/scans?limit=20` | Returns recent completed-scan summaries; `limit` accepts 1-100. |
| `GET` | `/scans/{scan_id}` | Returns persisted details for one scan. |
| `GET` | `/scans/{scan_id}/report` | Returns the persisted PDF report when available. |

The browser frontend uses `POST /scan`, `GET /scans`, and the report endpoint. The API permits local frontend origins at `http://127.0.0.1:5500` and `http://localhost:5500`.

## Technology stack

| Layer | Technology in this repository |
| --- | --- |
| Frontend | HTML, CSS, vanilla JavaScript |
| API | FastAPI, Uvicorn, Pydantic/Starlette stack |
| OCR | PaddleOCR 3.7.0 with PaddlePaddle 3.3.1; configured for `lang="en"` |
| Image processing | OpenCV, Pillow, NumPy |
| Rules and extraction | Python deterministic rule engine and spatial-analysis utilities |
| Persistence | SQLite (`data/scans.db`) |
| Reports | ReportLab |
| Tests | Python `unittest` |

## Project structure

```text
SIH26034/
+-- backend/
|   +-- app/
|   |   +-- main.py                 # FastAPI routes and scan orchestration
|   |   +-- runtime.py              # Paddle runtime configuration
|   |   +-- services/
|   |       +-- preprocessing.py
|   |       +-- ocr.py
|   |       +-- spatial_analysis.py
|   |       +-- field_extractor.py
|   |       +-- rules_engine.py
|   |       +-- evidence_renderer.py
|   |       +-- report_generator.py
|   |       +-- scan_repository.py
|   |       +-- scan_response.py
|   |       +-- scan_service.py
|   +-- tests/                      # 133 currently passing unit/API tests
|   +-- requirements.txt
+-- frontend/
|   +-- index.html
|   +-- styles.css
|   +-- app.js
+-- data/                            # Local scan artifacts and SQLite history
+-- runtime/                         # Local Python runtime artifacts
+-- models/
+-- rules/
+-- tests/
+-- .gitignore
+-- README.md
```
```

## Prerequisites and Windows local setup

The OCR environment requires **Python 3.13** in the project-root `.ocr-venv`. Confirm that Python 3.13 is installed before creating or recreating the environment. The pinned dependencies in `backend/requirements.txt` include FastAPI, PaddleOCR 3.7.0, PaddlePaddle 3.3.1, OpenCV, Pillow, ReportLab, and Uvicorn. PaddleOCR and PaddlePaddle are required for the real OCR pipeline.

From the repository root in PowerShell:

```powershell
# Confirm that the required interpreter is available.
py -3.13 --version

# Create or recreate the Python 3.13 OCR environment.
py -3.13 -m venv --clear .ocr-venv
.ocr-venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

PaddleOCR requires a Python/PaddlePaddle-compatible local environment. The included runtime configuration disables Paddle's MKLDNN/oneDNN setting before OCR initialization.

## Run locally

Start the backend from the repository root:

```powershell
.ocr-venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window, serve the static frontend:

```powershell
.ocr-venv\Scripts\python.exe -m http.server 5500 --directory frontend
```

Open `http://127.0.0.1:5500` in a browser. The frontend is configured to call the backend at `http://127.0.0.1:8000`.

## Tests

Run the complete suite from the repository root:

```powershell
.ocr-venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

**Current verified result: 133 tests passing.**

## Real validation example

A current local FreshBite label scan produced the structured product name **"Masala Potato Chips"**. Its result was `UNABLE_TO_VERIFY` with **8 PASS**, **0 FAIL**, **1 UNABLE_TO_VERIFY**, and **89% evidence coverage**; the unresolved item was LMPC-R6-10, where size relevance/dimensions could not be verified from the available evidence. This illustrates the intended conservative behavior: unresolved evidence triggers review instead of a fabricated pass or fail.

## Data and security notes

- Input is restricted to JPEG, PNG, and WEBP content types, capped at 10 MB, checked for non-empty content, and verified against its claimed image format.
- Uploaded files are assigned UUID-based stored filenames; raw images, processed images, evidence images, reports, and the SQLite history are local artifacts under `data/`.
- The report download route resolves and validates report paths inside `data/reports/` before serving them.
- This repository has no authentication, authorization, cloud storage, or production deployment configuration. Treat local scan artifacts as potentially sensitive and manage the `data/` directory accordingly.

## Regulatory references

The rule metadata currently links to the official Department of Consumer Affairs materials embedded in `backend/app/services/rules_engine.py`:

- Rule 6 declaration advisory: <https://consumeraffairs.nic.in/sites/default/files/file-uploads/latestnews/2023.01.18%20advisory%20for%20outer%20gift%20package%20declarations.pdf>
- Unit sale price advisory: <https://consumeraffairs.nic.in/sites/default/files/file-uploads/latestnews/230946.pdf>

The project is a technical screening implementation, not legal advice or a legal certification authority.

## Current limitations

- OCR is configured for English (`lang="en"`); multi-language OCR is not implemented.
- The rules evaluate extracted text and context only. They do not verify font size, readability, label placement, image completeness, or category-specific exemptions.
- OCR quality and extraction quality depend on the submitted image; uncertain evidence is intentionally reported as `UNABLE_TO_VERIFY`.
- Processing is single-image per request; batch processing is not implemented.
- Persistence is local SQLite, with no authentication or multi-user access control.
- The application is a local implementation; no production or cloud deployment is claimed.

## Future enhancements

- Add carefully validated multilingual OCR support.
- Add visual checks where suitable, such as declaration placement, font-size/readability assessment, and label-completeness review.
- Expand rule coverage and maintain rule metadata through a reviewed regulatory update process.
- Add batch workflows, authenticated roles, and deployment hardening only after their requirements are defined and implemented.

## SIH and team information

- **Project ID:** SIH26034
- **Project title:** Legal Metrology AI Compliance Inspection
- **Team member details:** Not stored in this repository.

## Project goal

Provide an explainable, conservative local workflow that helps reviewers screen package-label declarations using OCR, spatial evidence, structured extraction, and deterministic compliance rules while clearly identifying cases that still require human review.
