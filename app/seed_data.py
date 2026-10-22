"""The verified medicine catalogue that each business starts with.

Reference material only: a pharmacy's copy is seeded when the business (tenant)
is created, so every row carries its tenant id like everything else. Two rows
are deliberately unverified, to show what "belum disahkan" looks like.
"""
from __future__ import annotations


def ean13(prefix12: str) -> str:
    """Return the EAN-13 barcode (12 digits plus the check digit)."""
    if len(prefix12) != 12 or not prefix12.isdigit():
        raise ValueError("EAN-13 needs twelve digits before the check digit")
    total = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(prefix12)
    )
    return prefix12 + str((10 - total % 10) % 10)


def barcode_for(tenant_id: int, index: int) -> str:
    """A stable, distinct barcode per business: 955 (Malaysia) + tenant + item."""
    return ean13(f"955{tenant_id:03d}{index:06d}")


CATALOGUE: list[dict] = [
    {
        "name": "Paracetamol 500 mg",
        "brand": "Panadol",
        "active_ingredient": "Paracetamol",
        "strength": "500 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Haleon Malaysia Sdn Bhd",
        "uses": "Meredakan demam dan sakit ringan seperti sakit kepala, sakit gigi dan sakit badan.",
        "dosage_instructions": "Dewasa: 1 hingga 2 tablet setiap 4 hingga 6 jam selepas makan. Jangan melebihi 8 tablet dalam 24 jam.",
        "warnings": "Jangan diambil bersama ubat lain yang mengandungi paracetamol. Jangan melebihi dos yang disyorkan kerana boleh merosakkan hati. Dapatkan nasihat doktor jika demam berterusan lebih 3 hari.",
        "verified": 1,
    },
    {
        "name": "Paracetamol Sirap 120 mg/5 ml",
        "brand": "Panadol Anak",
        "active_ingredient": "Paracetamol",
        "strength": "120 mg/5 ml",
        "dosage_form": "Sirap",
        "manufacturer": "Haleon Malaysia Sdn Bhd",
        "uses": "Meredakan demam dan sakit ringan untuk kanak-kanak.",
        "dosage_instructions": "Kanak-kanak 1 hingga 5 tahun: 5 ml setiap 4 hingga 6 jam. Guna picagari dos yang disertakan.",
        "warnings": "Ikut dos mengikut umur dan berat badan. Jangan beri bersama ubat selesema yang mengandungi paracetamol. Rujuk doktor jika demam berterusan.",
        "verified": 1,
    },
    {
        "name": "Amoxicillin 500 mg",
        "brand": "Amoxil",
        "active_ingredient": "Amoxicillin trihydrate",
        "strength": "500 mg",
        "dosage_form": "Kapsul",
        "manufacturer": "GSK Pharmaceutical Sdn Bhd",
        "uses": "Antibiotik untuk jangkitan bakteria seperti jangkitan tekak, telinga dan saluran pernafasan.",
        "dosage_instructions": "Dewasa: 1 kapsul setiap 8 jam, atau mengikut preskripsi doktor. Habiskan seluruh kursus walaupun sudah berasa sihat.",
        "warnings": "Ubat ini memerlukan preskripsi. Jangan berkongsi. Berhenti dan dapatkan bantuan segera jika berlaku ruam, bengkak muka atau sesak nafas.",
        "verified": 1,
    },
    {
        "name": "Metformin 500 mg",
        "brand": "Glucophage",
        "active_ingredient": "Metformin hydrochloride",
        "strength": "500 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Merck Sdn Bhd",
        "uses": "Mengawal gula darah bagi pesakit diabetes jenis 2.",
        "dosage_instructions": "Dewasa: 1 tablet dua kali sehari bersama makanan, mengikut preskripsi doktor.",
        "warnings": "Ubat ini memerlukan preskripsi. Jangan hentikan tanpa nasihat doktor. Beritahu ahli farmasi jika ada masalah buah pinggang.",
        "verified": 1,
    },
    {
        "name": "Amlodipine 5 mg",
        "brand": "Norvasc",
        "active_ingredient": "Amlodipine besylate",
        "strength": "5 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Viatris Malaysia Sdn Bhd",
        "uses": "Mengawal tekanan darah tinggi dan mengurangkan risiko sakit jantung.",
        "dosage_instructions": "Dewasa: 1 tablet sekali sehari, pada masa yang sama setiap hari.",
        "warnings": "Ubat ini memerlukan preskripsi. Bangun perlahan-lahan jika berasa pening. Jangan berhenti tanpa nasihat doktor.",
        "verified": 1,
    },
    {
        "name": "Losartan 50 mg",
        "brand": "Cozaar",
        "active_ingredient": "Losartan potassium",
        "strength": "50 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Organon Malaysia Sdn Bhd",
        "uses": "Mengawal tekanan darah tinggi dan melindungi buah pinggang pesakit diabetes.",
        "dosage_instructions": "Dewasa: 1 tablet sekali sehari, mengikut preskripsi doktor.",
        "warnings": "Ubat ini memerlukan preskripsi. Tidak digalakkan semasa kehamilan. Dapatkan nasihat doktor jika berasa pening.",
        "verified": 1,
    },
    {
        "name": "Omeprazole 20 mg",
        "brand": "Losec",
        "active_ingredient": "Omeprazole",
        "strength": "20 mg",
        "dosage_form": "Kapsul",
        "manufacturer": "AstraZeneca Sdn Bhd",
        "uses": "Mengurangkan asid perut untuk gastrik, pedih ulu hati dan refluks asid.",
        "dosage_instructions": "Dewasa: 1 kapsul sekali sehari sebelum sarapan, selama tempoh yang dinasihatkan.",
        "warnings": "Ubat ini memerlukan preskripsi. Jangan telan bersama air yang banyak sekiranya kapsul tidak boleh dibuka. Rujuk doktor jika sakit berterusan.",
        "verified": 1,
    },
    {
        "name": "Cetirizine 10 mg",
        "brand": "Zyrtec",
        "active_ingredient": "Cetirizine dihydrochloride",
        "strength": "10 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Johnson & Johnson Sdn Bhd",
        "uses": "Melegakan alahan seperti gatal hidung, bersin, dan ruam gatal.",
        "dosage_instructions": "Dewasa dan kanak-kanak 12 tahun ke atas: 1 tablet sekali sehari.",
        "warnings": "Boleh menyebabkan rasa mengantuk. Elakkan memandu jika berasa mengantuk. Rujuk ahli farmasi jika mengambil ubat penenang lain.",
        "verified": 1,
    },
    {
        "name": "Loratadine 10 mg",
        "brand": "Clarityne",
        "active_ingredient": "Loratadine",
        "strength": "10 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Bayer Malaysia Sdn Bhd",
        "uses": "Melegakan alahan bermusim dan gatal-gatal pada kulit.",
        "dosage_instructions": "Dewasa dan kanak-kanak 2 tahun ke atas: 1 tablet sekali sehari.",
        "warnings": "Rujuk ahli farmasi jika hamil, menyusu atau mempunyai masalah hati.",
        "verified": 1,
    },
    {
        "name": "Ibuprofen 400 mg",
        "brand": "Brufen",
        "active_ingredient": "Ibuprofen",
        "strength": "400 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Abbott Laboratories Sdn Bhd",
        "uses": "Melegakan sakit, demam dan keradangan seperti sakit sendi dan sakit haid.",
        "dosage_instructions": "Dewasa: 1 tablet setiap 6 hingga 8 jam selepas makan. Jangan melebihi 3 tablet dalam 24 jam tanpa nasihat doktor.",
        "warnings": "Ambil selepas makan. Elakkan jika mempunyai ulser perut, masalah buah pinggang atau hamil. Jangan ambil bersama ubat sakit lain tanpa nasihat.",
        "verified": 1,
    },
    {
        "name": "Mefenamic acid 500 mg",
        "brand": "Ponstan",
        "active_ingredient": "Mefenamic acid",
        "strength": "500 mg",
        "dosage_form": "Tablet",
        "manufacturer": "Pfizer Malaysia Sdn Bhd",
        "uses": "Melegakan sakit haid dan sakit ringan lain.",
        "dosage_instructions": "Dewasa: 1 tablet tiga kali sehari selepas makan, selama tidak melebihi 7 hari.",
        "warnings": "Ambil selepas makan. Elakkan jika mempunyai ulser perut atau masalah buah pinggang. Rujuk doktor jika sakit haid berterusan.",
        "verified": 1,
    },
    {
        "name": "Salbutamol Inhaler 100 mcg",
        "brand": "Ventolin",
        "active_ingredient": "Salbutamol sulfate",
        "strength": "100 mcg/dos",
        "dosage_form": "Inhaler aerosol",
        "manufacturer": "GSK Pharmaceutical Sdn Bhd",
        "uses": "Melegakan sesak nafas dan wheezing bagi pesakit asma.",
        "dosage_instructions": "Dewasa: 1 hingga 2 sedutan apabila perlu, atau mengikut pelan rawatan doktor. Bilas mulut selepas digunakan.",
        "warnings": "Ubat ini memerlukan preskripsi. Dapatkan bantuan kecemasan jika sesak nafas tidak reda atau bertambah teruk.",
        "verified": 1,
    },
    {
        "name": "Chlorpheniramine 4 mg",
        "brand": "Piriton",
        "active_ingredient": "Chlorpheniramine maleate",
        "strength": "4 mg",
        "dosage_form": "Tablet",
        "manufacturer": "GlaxoSmithKline Sdn Bhd",
        "uses": "Melegakan bersin, gatal hidung dan ruam alahan.",
        "dosage_instructions": "Dewasa: 1 tablet setiap 4 hingga 6 jam, tidak melebihi 6 tablet sehari.",
        "warnings": "Menyebabkan rasa mengantuk. Jangan memandu selepas mengambilnya. Elakkan alkohol.",
        "verified": 1,
    },
    {
        "name": "Oral Rehydration Salt",
        "brand": "ORS Plus",
        "active_ingredient": "Sodium chloride, potassium chloride, sodium citrate, glucose",
        "strength": "1 sachet / 200 ml",
        "dosage_form": "Serbuk untuk larutan",
        "manufacturer": "Pharmaniaga Manufacturing Berhad",
        "uses": "Menggantikan cecair dan garam yang hilang akibat cirit-birit atau muntah.",
        "dosage_instructions": "Larutkan 1 sachet dalam 200 ml air minuman yang bersih. Minum sedikit-sedikit dan kerap.",
        "warnings": "Gunakan air yang telah dimasak. Buang larutan yang lebih 24 jam. Dapatkan bantuan jika cirit-birit berterusan atau berlaku dehidrasi teruk.",
        "verified": 1,
    },
    {
        "name": "Hand Sanitiser Gel 70%",
        "brand": "Dettol",
        "active_ingredient": "Ethanol",
        "strength": "70% v/v",
        "dosage_form": "Gel",
        "manufacturer": "Reckitt Benckiser Malaysia Sdn Bhd",
        "uses": "",
        "dosage_instructions": "",
        "warnings": "",
        "verified": 0,
    },
    {
        "name": "Multivitamin Harian",
        "brand": "Seven Seas",
        "active_ingredient": "Campuran vitamin dan mineral",
        "strength": "1 tablet",
        "dosage_form": "Tablet",
        "manufacturer": "Merck Sdn Bhd",
        "uses": "",
        "dosage_instructions": "",
        "warnings": "",
        "verified": 0,
    },
]
