# REDCap-Girder Integration POC

A Proof of Concept demonstrating the integration between REDCap (metadata collection) and Girder (file storage) for medical research data management.

## 🎯 What This POC Demonstrates

This POC shows how to:
1. **Upload files** to local storage via REDCap mimic interface
2. **Sync files** to Girder in an organized folder structure
3. **Manage folder hierarchy** automatically (CHU → Patient → Visit → Document Type)

## 📋 Prerequisites

- Python 3.10 or higher
- Access to a Girder instance (or run locally on port 8080)
- Git

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/vickyapril02/girder-redcap-mimic-sync.git
cd girder-redcap-mimic-sync
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
GIRDER_API_URL=http://localhost:8080/api/v1
GIRDER_API_KEY=your-girder-api-key-here
GIRDER_ROOT_FOLDER_ID=your-root-folder-id-here
```

**How to get these values:**
- **GIRDER_API_URL**: Your Girder URL + `/api/v1` (e.g., `http://localhost:8080/api/v1`)
- **GIRDER_API_KEY**: Generate in Girder UI → User Settings → API Keys → Create API Key
- **GIRDER_ROOT_FOLDER_ID**: Open a folder in Girder, copy the ID from the URL

### 5. Create Folder Structure in Girder

Run the schema creation script:

```bash
python scripts/create_girder_schema.py
```

This creates the folder structure:
```
ROOT_FOLDER/
├── CHU_Bordeaux/
│   ├── Patient_001/
│   │   ├── Inclusion M0/
│   │   │   ├── Bilan Biologique/
│   │   │   ├── Consentement_Eclaire/
│   │   │   └── Dosage des β HCG/
│   │   └── (other visits...)
│   └── Patient_002/
└── (other hospitals...)
```

### 6. Start the Server

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 7. Access the Web Interface

Open your browser:
```
http://localhost:8000/redcap-mimic
```

## 📖 How to Use

### Upload a File

1. Expand the tree structure: **Hospital → Patient → Visit → Document Type**
2. Click the **"Upload"** button next to any document type
3. Select a file (DICOM, ZIP, PDF, etc.)
4. File is saved locally and shows **"Pending"** status

### Sync to Girder

1. Click the **"Sync with Girder"** button next to the uploaded file
2. File uploads to Girder in the correct folder
3. Status changes to **"Synced"**

### Verify in Girder

1. Open Girder UI: `http://localhost:8080`
2. Navigate to: `ROOT_FOLDER/CHU_Bordeaux/Patient_001/Inclusion M0/Bilan Biologique/`
3. Your file should be there!

## 📁 Project Structure

```
girder-redcap-mimic-sync/
├── app.py                      # FastAPI main application
├── models.py                   # Data models
├── database.py                 # SQLite database operations
├── girder_client.py            # Girder API client
├── redcap_mimic.html          # Web interface
├── scripts/
│   └── create_girder_schema.py # Create folder structure
├── sync/                       # Sync utilities
│   ├── __init__.py
│   └── extract_sync.py
├── test_webhook.py            # Test script
├── requirements.txt           # Python dependencies
├── .gitignore                 # Git ignore rules
└── README.md                  # This file
```

## 🔧 API Endpoints

- `GET /` - Health check
- `GET /health` - Detailed health check
- `GET /redcap-mimic` - Web interface
- `GET /api/structure` - Get folder structure
- `POST /api/upload` - Upload file to local disk
- `POST /api/sync-to-girder` - Sync file to Girder
- `GET /api/files/{document_type_id}` - List files

## 🐛 Troubleshooting

### Server won't start
- Check if port 8000 is available
- Verify Python version: `python3 --version` (should be 3.10+)
- Check dependencies: `pip list`

### Cannot connect to Girder
- Verify `.env` file has correct values
- Test Girder: `curl http://localhost:8080/api/v1/system/version`
- Check if Girder is running

### Files not syncing
- Run `python scripts/create_girder_schema.py` again
- Check server logs for errors
- Verify `GIRDER_ROOT_FOLDER_ID` is correct

### Database errors
- Delete `redcap_mimic.db` and restart (will be recreated)
- Check file permissions

## 📊 Architecture

See `SIMPLE_ARCHITECTURE.md` for a visual overview of the system architecture.

## 🔒 Security Note

- Never commit `.env` file (it's in .gitignore)
- Never commit uploaded files
- Keep your Girder API key secure

## 📝 License

This is a proof of concept for demonstration purposes.

## 🤝 Support

For issues:
1. Check server logs in terminal
2. Verify environment variables
3. Review error messages in web interface
