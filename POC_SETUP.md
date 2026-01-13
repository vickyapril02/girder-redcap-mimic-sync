# REDCap-Girder Integration POC - Setup Guide

## What Was Created

### 1. Database Module (`database.py`)
- SQLite database with schema for:
  - Centers (hospitals)
  - Patients
  - Visits (Inclusion M0, Preinclusion M-6, Visite M12, Visite M24)
  - Document Types (Bilan Biologique, Consentement_Eclaire, Dosage des β HCG, ECG 12 derivations)
  - Files
- Pre-populated with:
  - 3 Hospitals: CHU Bordeaux, CHU Paris, CHU Toulouse
  - 2 Patients per hospital (Patient_001, Patient_002)
  - 4 Visits per patient
  - Document types per visit (as specified)

### 2. Enhanced FastAPI (`app.py`)
- New endpoints:
  - `GET /redcap-mimic` - Serve the HTML interface
  - `GET /api/structure` - Get complete structure for tree view
  - `POST /api/upload` - Upload files to REDCap mimic
  - `GET /api/files/{document_type_id}` - Get files for a document type

### 3. HTML Interface (`redcap_mimic.html`)
- Collapsible tree view showing:
  - Hospitals → Patients → Visits → Document Types
- Upload button for each document type
- File list showing uploaded files with sync status

## How to Run

1. **Start the FastAPI server:**
   ```bash
   cd /Users/vigneshwar.gurunatha/Desktop/redcap/poc-redcap
   source bin/activate
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Access the interface:**
   - Open browser: `http://localhost:8000/redcap-mimic`
   - You'll see the tree structure with all hospitals, patients, visits, and document types

3. **Upload files:**
   - Expand the tree to find the document type you want
   - Click "Upload" button
   - Select a file
   - File will be saved to: `uploads/{center_code}/{patient_id}/{visit_code}/{document_code}/`

## Database Location

- SQLite database: `redcap_mimic.db` (created in the same directory)
- File uploads: `uploads/` directory

## Structure

```
REDCap-Girder Integration
├── CHU Bordeaux
│   ├── Patient_001
│   │   ├── Inclusion M0
│   │   │   ├── Bilan Biologique [Upload]
│   │   │   ├── Consentement_Eclaire [Upload]
│   │   │   └── Dosage des β HCG [Upload]
│   │   ├── Preinclusion M-6
│   │   │   ├── Bilan Biologique [Upload]
│   │   │   ├── Consentement_Eclaire [Upload]
│   │   │   ├── Dosage des β HCG [Upload]
│   │   │   └── ECG 12 derivations [Upload]
│   │   ├── Visite M12
│   │   │   └── (same as Inclusion M0)
│   │   └── Visite M24
│   │       └── (same as Inclusion M0)
│   └── Patient_002
│       └── (same structure)
├── CHU Paris
│   └── (same structure)
└── CHU Toulouse
    └── (same structure)
```

## Next Steps

1. **Test file uploads** - Upload files to different document types
2. **Implement Girder sync** - Add "Sync with Girder" functionality
3. **Add validation** - Ensure structure matches before syncing

## Notes

- Database is automatically initialized on first run
- Files are stored locally in the `uploads/` directory
- All existing endpoints (`/redcap/webhook`, `/health`, etc.) remain functional


