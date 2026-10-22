# Requirements

Version 1: **The must-haves only**. The source of truth is `blueprint.json`; this file explains it.

## Roles
| Role | What they do |
|---|---|
| Registered user | signs in to scan medicine barcodes, view medicine information, access scan history and save medicines to favourites |
| Pharmacist/health care professional | Reviews medicine information, checks dosage instructions and warnings, and helps verify medicine information where authorised. |
| Guest User | Can scan and view permitted public information without creating an account. |
| System Administrator | Manages system configuration, data sources, integrations and technical operations. Has access only to the administrative functions assigned to this role. |

## Features
| Id | Feature | Priority | Used by | AI | What it does |
|---|---|---|---|---|---|
| F1 | barcode scanner | Must, version 1 | Registered user |  | Scan medicine barcodes using a mobile camera or compatible barcode scanner |
| F2 | Medicine Information Lookup | Must, version 1 | Registered user |  | Search a medicine database using the scanned barcode. |
| F3 | Medicines details page | Must, version 1 | Registered user |  | Display the medicine name, brand, active ingredient, strength, dosage form and manufacturer when verified information is available. |

## Use cases (version 1)

### UC1 · barcode scanner (F1)
- Actor: Registered user
- Goal: To scan a medicine barcode using a camera or supported barcode scanner and automatically retrieve the matching medicine information, including its name, active ingredient, strength, dosage form, uses, administration instructions and warnings when verified information is available.

Main steps:
The user opens CODE4CARE and selects Scan Medicine.
The system requests camera permission if it has not already been granted.
The user grants permission and positions the medicine barcode within the scanning area.
The system detects and decodes the barcode automatically.
The system validates the barcode and searches the medicine database for a matching record.
The system retrieves the available verified medicine information.
The system automatically displays the medicine details page when a reliable match is found.
The user reviews the medicine name, active ingredient, strength, dosage form, uses, administration instructions and warnings.
If no matching record is found, the system displays a message and offers manual barcode entry or medicine search.

Errors and edge cases:
- Missing or invalid input: a message says what to fix, and nothing is saved.
- Signed out, or a role without permission: refused.

Acceptance criteria (tests in `tests/acceptance/test_f1_barcode_scanner.py`):
- AC1.1 Given a signed-in Account owner, when they scan medicine barcodes using a mobile camera or compatible barcode scanner, then the result is saved for their business only
- AC1.2 Given a user without permission, when they try it, then it is refused
- AC1.3 Given invalid input, when it is submitted, then a clear message shows and nothing is saved

### UC2 · Medicine Information Lookup (F2)
- Actor: Registered user
- Goal: Account owner can search a medicine database using the scanned barcode.

Main steps:
1. Account owner opens Medicine Information Lookup.
2. They enter or choose what it needs, and submit.
3. The server checks the input and the permission, and saves it for this business only.
4. The result is shown.

Errors and edge cases:
- Missing or invalid input: a message says what to fix, and nothing is saved.
- Signed out, or a role without permission: refused.

Acceptance criteria (tests in `tests/acceptance/test_f2_medicine_information_lookup.py`):
- AC2.1 Given a signed-in Account owner, when they search a medicine database using the scanned barcode., then the result is saved for their business only
- AC2.2 Given a user without permission, when they try it, then it is refused
- AC2.3 Given invalid input, when it is submitted, then a clear message shows and nothing is saved

### UC3 · Medicines details page (F3)
- Actor: Registered user
- Goal: Registered user can display the medicine name, brand, active ingredient, strength, dosage form and manufacturer when verified information is available.

Main steps:
1. Registered user opens Medicines details page.
2. They enter or choose what it needs, and submit.
3. The server checks the input and the permission, and saves it for this business only.
4. The result is shown.

Errors and edge cases:
- Missing or invalid input: a message says what to fix, and nothing is saved.
- Signed out, or a role without permission: refused.

Acceptance criteria (tests in `tests/acceptance/test_f3_medicines_details_page.py`):
- AC3.1 Given a signed-in Registered user, when they display the medicine name, brand, active ingredient, strength, dosage form and manufacturer when verified information is available., then the result is saved for their business only
- AC3.2 Given a user without permission, when they try it, then it is refused
- AC3.3 Given invalid input, when it is submitted, then a clear message shows and nothing is saved

## Integrations
- Email sending

## Platforms
- A web app (works on phones too)

## Out of scope for version 1
- Anything not listed above.

## Data
See docs/DATA_MODEL.md.
