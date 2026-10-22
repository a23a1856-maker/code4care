# Product requirements

**CODE4CARE**: CODE4CARE helps community pharmacies in Malaysia identify medicines by barcode and provide customers with clear, reliable medicine information, including uses, dosage instructions, and safety warnings from verified sources.

## Customer and problem
- Who pays: Community pharmacies and independent pharmacy owners in Malaysia.
- Problem: Customers frequently ask us about medicines, their uses, and how to take them. Our staff spend time searching for reliable information, explaining the same details repeatedly, and helping customers understand medicine labels.
- Today: Pharmacy staff manually inspect medicine packaging, read product leaflets, search medicine databases, consult pharmacists, or refer to official medicine information sources.
- How often: 0 tasks per customer a month
- Languages: Bahasa Melayu; channel: A web app or web chat

## Who uses it
- Registered user: signs in to scan medicine barcodes, view medicine information, access scan history and save medicines to favourites
- Pharmacist/health care professional: Reviews medicine information, checks dosage instructions and warnings, and helps verify medicine information where authorised.
- Guest User: Can scan and view permitted public information without creating an account.
- System Administrator: Manages system configuration, data sources, integrations and technical operations. Has access only to the administrative functions assigned to this role.

## Version 1 does
- barcode scanner: Scan medicine barcodes using a mobile camera or compatible barcode scanner
- Medicine Information Lookup: Search a medicine database using the scanned barcode.
- Medicines details page: Display the medicine name, brand, active ingredient, strength, dosage form and manufacturer when verified information is available.
- Each customer’s data is kept apart; people sign in, and each role may do only what docs/AUTH.md allows.

## Version 1 does not do
- Anything not listed above.

## Success
- The quality targets in docs/QUALITY.md pass.
- 3 paying customers in the first three months.
