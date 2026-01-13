from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from models import Patient
from girder_client import (
    get_or_create_folder,
    set_metadata,
    get_folder_by_id,
    upload_file,
    set_folder_access,
    find_folder,
    GirderError
)
from database import Database
import logging
import os
from pathlib import Path
from typing import List
import aiofiles
import sqlite3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="REDCap to Girder Sync",
    description="Webhook endpoint to sync REDCap patient data to Girder",
    version="1.0.0"
)

# Root folder ID where all CHU folders will be created
ROOT_FOLDER_ID = os.getenv("GIRDER_ROOT_FOLDER_ID", "6951dc52c496589ab697c8ac")

# Initialize database
db = Database()

# Create uploads directory
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "REDCap to Girder Sync",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/redcap/webhook",
            "file_upload": "/redcap/upload",
            "health": "/health",
            "mock_interface": "/mock-redcap",
            "redcap_mimic": "/redcap-mimic",
            "structure_api": "/api/structure",
            "upload_api": "/api/upload"
        }
    }


@app.get("/mock-redcap")
async def mock_redcap():
    """Serve the mock REDCap interface"""
    html_path = Path(__file__).parent / "mock_redcap.html"
    if html_path.exists():
        return FileResponse(html_path)
    else:
        raise HTTPException(status_code=404, detail="Mock REDCap interface not found")


@app.post("/redcap/webhook")
async def redcap_webhook(patient: Patient, request: Request):
    """
    Webhook endpoint to receive patient data from REDCap and sync to Girder.
    
    Creates nested folder structure: ROOT/CHU_Center/Patient_ID/
    and sets patient metadata on the patient folder.
    
    Args:
        patient: Patient data model containing center_code, patient_id, age, sex
        
    Returns:
        JSON response with status and folder information
    """
    try:
        logger.info(f"Received webhook for patient: {patient.patient_id} from center: {patient.center_code}")
        
        # Step 1: Get or create CHU center folder
        chu_folder_name = f"CHU_{patient.center_code}"
        logger.info(f"Looking for CHU folder: {chu_folder_name}")
        
        try:
            chu_folder = get_or_create_folder(chu_folder_name, ROOT_FOLDER_ID, public=True)
            # Ensure folder is accessible
            try:
                set_folder_access(chu_folder["_id"], public=True)
            except GirderError:
                logger.warning(f"Could not set access for CHU folder, continuing...")
            logger.info(f"CHU folder '{chu_folder_name}' ready with ID: {chu_folder['_id']}")
        except GirderError as e:
            logger.error(f"Failed to get/create CHU folder: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to access CHU folder: {str(e)}"
            )
        
        # Step 2: Get or create patient folder within CHU folder
        logger.info(f"Looking for patient folder: {patient.patient_id}")
        
        try:
            patient_folder = get_or_create_folder(patient.patient_id, chu_folder["_id"], public=True)
            # Ensure folder is accessible
            try:
                set_folder_access(patient_folder["_id"], public=True)
            except GirderError:
                # If setting access fails, continue anyway (folder might already be accessible)
                logger.warning(f"Could not set access for patient folder, continuing...")
            logger.info(f"Patient folder '{patient.patient_id}' ready with ID: {patient_folder['_id']}")
        except GirderError as e:
            logger.error(f"Failed to get/create patient folder: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to access patient folder: {str(e)}"
            )
        
        # Step 3: Set patient metadata
        patient_data = patient.dict()
        try:
            set_metadata(patient_folder["_id"], patient_data)
            logger.info(f"Successfully synced patient {patient.patient_id} to Girder")
        except GirderError as e:
            logger.error(f"Failed to set metadata: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set patient metadata: {str(e)}"
            )
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "synced",
                "message": f"Patient {patient.patient_id} successfully synced to Girder",
                "folder_structure": {
                    "root": ROOT_FOLDER_ID,
                    "chu_folder": {
                        "name": chu_folder_name,
                        "id": chu_folder["_id"]
                    },
                    "patient_folder": {
                        "name": patient.patient_id,
                        "id": patient_folder["_id"]
                    }
                },
                "patient_data": patient_data
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.post("/redcap/upload")
async def upload_patient_files(
    center_code: str = Form(...),
    patient_id: str = Form(...),
    age: int = Form(...),
    sex: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    Direct file upload endpoint.
    Accepts patient metadata + files (DICOM, images, etc.) in multipart form.
    
    This endpoint:
    1. Creates/finds CHU and patient folders
    2. Sets patient metadata
    3. Uploads all files to the patient folder
    """
    try:
        logger.info(f"Received file upload for patient: {patient_id} from center: {center_code}")
        logger.info(f"Number of files: {len(files)}")
        
        # Step 1: Get or create CHU center folder
        chu_folder_name = f"CHU_{center_code}"
        try:
            chu_folder = get_or_create_folder(chu_folder_name, ROOT_FOLDER_ID, public=True)
            # Ensure folder is accessible
            try:
                set_folder_access(chu_folder["_id"], public=True)
            except GirderError:
                logger.warning(f"Could not set access for CHU folder, continuing...")
            logger.info(f"CHU folder '{chu_folder_name}' ready with ID: {chu_folder['_id']}")
        except GirderError as e:
            logger.error(f"Failed to get/create CHU folder: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to access CHU folder: {str(e)}"
            )
        
        # Step 2: Get or create patient folder
        try:
            patient_folder = get_or_create_folder(patient_id, chu_folder["_id"], public=True)
            # Ensure folder is accessible
            try:
                set_folder_access(patient_folder["_id"], public=True)
            except GirderError:
                logger.warning(f"Could not set access for patient folder, continuing...")
            logger.info(f"Patient folder '{patient_id}' ready with ID: {patient_folder['_id']}")
        except GirderError as e:
            logger.error(f"Failed to get/create patient folder: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to access patient folder: {str(e)}"
            )
        
        # Step 3: Set patient metadata
        patient_data = {
            "center_code": center_code,
            "patient_id": patient_id,
            "age": age,
            "sex": sex
        }
        try:
            set_metadata(patient_folder["_id"], patient_data)
            logger.info(f"Set metadata for patient {patient_id}")
        except GirderError as e:
            logger.error(f"Failed to set metadata: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set patient metadata: {str(e)}"
            )
        
        # Step 4: Upload files (ZIP files uploaded as-is, no extraction)
        uploaded_files = []
        failed_files = []
        
        for file in files:
            try:
                file_contents = await file.read()
                file_name = file.filename or "unnamed_file"
                
                # Upload file directly (ZIP files uploaded as-is for testing)
                file_result = upload_file(
                    file_contents,
                    patient_folder["_id"],
                    file_name
                )
                uploaded_files.append({
                    "name": file_name,
                    "id": file_result.get("_id"),
                    "size": file_result.get("size", len(file_contents))
                })
                logger.info(f"Successfully uploaded file: {file_name}")
                    
            except Exception as e:
                logger.error(f"Failed to upload file {file.filename}: {str(e)}")
                failed_files.append({
                    "name": file.filename,
                    "error": str(e)
                })
        
        message = f"Patient {patient_id} and {len(uploaded_files)} file(s) successfully synced to Girder"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "synced",
                "message": message,
                "folder_structure": {
                    "root": ROOT_FOLDER_ID,
                    "chu_folder": {
                        "name": chu_folder_name,
                        "id": chu_folder["_id"]
                    },
                    "patient_folder": {
                        "name": patient_id,
                        "id": patient_folder["_id"]
                    }
                },
                "patient_data": patient_data,
                "uploaded_files": uploaded_files,
                "upload_summary": {
                    "total_files": len(uploaded_files)
                },
                "failed_files": failed_files if failed_files else None
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing file upload: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Try to access root folder to verify Girder connection
        get_folder_by_id(ROOT_FOLDER_ID)
        return {
            "status": "healthy",
            "girder_connection": "ok",
            "root_folder_id": ROOT_FOLDER_ID
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "girder_connection": "failed",
                "error": str(e)
            }
        )


# ============================================================================
# REDCap Mimic Endpoints
# ============================================================================

@app.get("/redcap-mimic")
async def redcap_mimic_interface():
    """Serve the REDCap mimic interface"""
    html_path = Path(__file__).parent / "redcap_mimic.html"
    if html_path.exists():
        return FileResponse(html_path)
    else:
        raise HTTPException(status_code=404, detail="REDCap mimic interface not found")


@app.get("/api/structure")
async def get_structure():
    """Get complete structure for tree view"""
    try:
        structure = db.get_full_structure()
        return {"structure": structure}
    except Exception as e:
        logger.error(f"Error getting structure: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading structure: {str(e)}")


@app.post("/api/upload")
async def upload_file_to_redcap(
    document_type_id: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload file to local disk (for POC demonstration).
    
    This demonstrates the workflow: Upload to local → Sync to Girder.
    Files are saved to local disk and can be synced later using /api/sync-to-girder.
    
    Flow:
    1. Get document type info from database
    2. Save file to local disk (uploads/ directory)
    3. Store file record in database
    4. Return file_id for later sync
    """
    try:
        # Get document type info
        doc_type = db.get_document_type(document_type_id)
        if not doc_type:
            raise HTTPException(status_code=404, detail="Document type not found")
        
        # Create directory structure
        center_code = doc_type['center_code']
        patient_id = doc_type['patient_id']
        visit_code = doc_type['visit_code']
        doc_code = doc_type['document_code']
        
        file_dir = UPLOADS_DIR / center_code / patient_id / visit_code / doc_code
        file_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file to local disk
        file_path = file_dir / file.filename
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        file_size = file_path.stat().st_size
        mime_type = file.content_type or "application/octet-stream"
        
        # Save to database
        file_id = db.create_file(
            document_type_id, file.filename, str(file_path), file_size, mime_type
        )
        
        logger.info(f"File uploaded to local disk: {file.filename} (ID: {file_id})")
        
        return {
            "status": "uploaded",
            "file_id": file_id,
            "filename": file.filename,
            "file_size": file_size,
            "message": "File uploaded successfully. Click 'Sync with Girder' to sync."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@app.post("/api/upload-local")
async def upload_file_to_local(
    document_type_id: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload file to local disk (OLD workflow for POC demonstration).
    
    This demonstrates the OLD workflow: Upload to local → Sync to Girder.
    Files are saved to local disk and can be synced later using /api/sync-to-girder.
    
    Flow:
    1. Get document type info from database
    2. Save file to local disk (uploads/ directory)
    3. Store file record in database
    4. Return file_id for later sync
    """
    try:
        # Get document type info
        doc_type = db.get_document_type(document_type_id)
        if not doc_type:
            raise HTTPException(status_code=404, detail="Document type not found")
        
        # Create directory structure
        center_code = doc_type['center_code']
        patient_id = doc_type['patient_id']
        visit_code = doc_type['visit_code']
        doc_code = doc_type['document_code']
        
        file_dir = UPLOADS_DIR / center_code / patient_id / visit_code / doc_code
        file_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file to local disk
        file_path = file_dir / file.filename
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        file_size = file_path.stat().st_size
        mime_type = file.content_type or "application/octet-stream"
        
        # Save to database
        file_id = db.create_file(
            document_type_id, file.filename, str(file_path), file_size, mime_type
        )
        
        logger.info(f"File uploaded to local disk: {file.filename} (ID: {file_id})")
        
        return {
            "status": "uploaded",
            "file_id": file_id,
            "filename": file.filename,
            "file_size": file_size,
            "message": "File uploaded to local disk. Click 'Sync with Girder' to sync.",
            "workflow": "local"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file to local: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@app.get("/api/files/{document_type_id}")
async def get_files(document_type_id: int):
    """Get files for a document type"""
    try:
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM files WHERE document_type_id = ? ORDER BY uploaded_at DESC
        """, (document_type_id,))
        files = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"files": files}
    except Exception as e:
        logger.error(f"Error getting files: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading files: {str(e)}")


@app.post("/api/sync-to-girder")
async def sync_to_girder(file_id: int = Form(...)):
    """
    Sync uploaded file to Girder with structure validation
    
    Validates that the exact folder structure exists in Girder:
    - Center (CHU_{center_code})
    - Patient (patient_id)
    - Visit (visit_name)
    - Document Type (document_name)
    
    If all levels exist, uploads file to Girder and marks as synced.
    """
    try:
        # Get file with full path information
        file_info = db.get_file_with_path_info(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if already synced
        if file_info.get('synced_to_girder'):
            return {
                "status": "already_synced",
                "message": "File is already synced to Girder",
                "girder_file_id": file_info.get('girder_file_id')
            }
        
        # Validate structure exists in Girder using database lookup (FAST!)
        center_code = file_info['center_code']
        patient_id = file_info['patient_id']
        visit_name = file_info['visit_name']
        document_name = file_info['document_name']
        center_girder_name = f"CHU_{center_code}"
        
        # Lookup Girder folder_id from database (much faster than API calls)
        doc_folder_id = db.get_document_folder_id(
            center_code=center_code,
            patient_id=patient_id,
            visit_name=visit_name,
            document_name=document_name
        )
        
        if not doc_folder_id:
            raise HTTPException(
                status_code=404,
                detail=f"Folder structure not found in database. Please run create_girder_schema.py first."
            )
        
        # Verify folder exists in Girder
        try:
            folder_info = get_folder_by_id(doc_folder_id)
        except GirderError as e:
            raise HTTPException(
                status_code=404,
                detail=f"Folder exists in database but not in Girder. Please run create_girder_schema.py again."
            )
        
        # Step 5: Upload file to Girder
        file_path = Path(file_info['file_path'])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            girder_file = upload_file(file_data, doc_folder_id, file_info['filename'])
            
            # Mark as synced
            db.mark_file_synced(file_id, girder_file['_id'])
            
            logger.info(f"File {file_info['filename']} synced to Girder successfully")
            
            return {
                "status": "synced",
                "message": f"File '{file_info['filename']}' successfully synced to Girder",
                "girder_file_id": girder_file['_id'],
                "folder_path": f"{center_girder_name}/{patient_id}/{visit_name}/{document_name}"
            }
        except GirderError as e:
            logger.error(f"Failed to upload file to Girder: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to upload to Girder: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing file to Girder: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error syncing file: {str(e)}")

