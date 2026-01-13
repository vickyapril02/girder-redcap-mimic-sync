#!/usr/bin/env python3
"""
Extract and Sync Module for REDCap-Girder Integration

WHAT THIS MODULE DOES:
=====================
1. EXTRACT PHASE:
   - Reads all files from REDCap mimic SQLite database
   - Filters to only files that haven't been synced yet (synced_to_girder = 0)
   - Gets full path information for each file (center → patient → visit → document)

2. SYNC PHASE:
   - For each unsynced file:
     a. Validates folder structure exists in Girder
     b. Finds the correct Girder folder path
     c. Uploads the file to Girder
     d. Marks file as synced in database

3. VALIDATION:
   - Checks that folder structure exists before uploading
   - Handles errors gracefully (logs failures, continues with other files)
   - Returns summary of sync results

HOW IT WORKS WITH REAL REDCAP:
==============================
In production, instead of reading from SQLite, you would:
1. Use REDCap API to query files:
   - GET /api/files.php (get file metadata)
   - GET /api/export.php (export records with file fields)
   
2. Download files from REDCap:
   - GET /api/files.php?action=download&record=...&field=...
   
3. Upload to Girder:
   - Same logic as this module
   - Match REDCap record structure to Girder folder structure

This module is the "mimic" version - it reads from SQLite instead of REDCap API.
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Database
from girder_client import (
    find_folder,
    get_folder_by_id,
    upload_file,
    GirderError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_unsynced_files(db: Database) -> List[Dict]:
    """
    Extract all unsynced files from the database.
    
    WHAT IT DOES:
    - Queries SQLite database for files where synced_to_girder = 0
    - Gets full path information (center, patient, visit, document type)
    - Returns list of file dictionaries with all metadata
    
    Args:
        db: Database instance
        
    Returns:
        List of file dictionaries with path information
    """
    logger.info("📖 Extracting unsynced files from database...")
    
    # Query database for all files that haven't been synced
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all unsynced files with full path information
    cursor.execute("""
        SELECT f.*, 
               dt.document_name, dt.document_code, dt.girder_folder_id as doc_girder_folder_id,
               v.visit_name, v.visit_code, v.girder_folder_id as visit_girder_folder_id,
               p.patient_id, p.girder_folder_id as patient_girder_folder_id,
               c.code as center_code, c.name as center_name, c.girder_folder_id as center_girder_folder_id
        FROM files f
        JOIN document_types dt ON f.document_type_id = dt.id
        JOIN visits v ON dt.visit_id = v.id
        JOIN patients p ON v.patient_id = p.id
        JOIN centers c ON p.center_id = c.id
        WHERE f.synced_to_girder = 0
        ORDER BY f.uploaded_at ASC
    """)
    
    files = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"   Found {len(files)} unsynced file(s)")
    return files


def find_girder_folder_path(
    file_info: Dict,
    root_folder_id: str
) -> Tuple[str, str]:
    """
    Find the correct Girder folder path for a file.
    
    WHAT IT DOES:
    - Takes file information (center, patient, visit, document)
    - Traverses Girder folder structure to find the document type folder
    - Returns the folder ID where the file should be uploaded
    
    Args:
        file_info: Dictionary with file and path information
        root_folder_id: Root folder ID in Girder
        
    Returns:
        Tuple of (folder_id, folder_path_string)
        
    Raises:
        ValueError: If folder structure doesn't exist in Girder
    """
    center_code = file_info['center_code']
    center_name = file_info['center_name']
    patient_id = file_info['patient_id']
    visit_name = file_info['visit_name']
    document_name = file_info['document_name']
    
    center_girder_name = f"CHU_{center_code}"
    
    # Step 1: Find Center folder
    # First check if we have the folder ID stored in database
    center_folder_id = file_info.get('center_girder_folder_id')
    
    if center_folder_id:
        # Verify folder still exists
        try:
            get_folder_by_id(center_folder_id)
        except GirderError:
            # Folder doesn't exist, need to find it
            center_folder_id = None
    
    if not center_folder_id:
        # Find center folder by name
        center_folder = find_folder(center_girder_name, root_folder_id)
        if not center_folder:
            raise ValueError(
                f"Center '{center_girder_name}' not found in Girder. "
                f"Please run create_girder_schema.py first."
            )
        center_folder_id = center_folder['_id']
    
    # Step 2: Find Patient folder
    patient_folder_id = file_info.get('patient_girder_folder_id')
    
    if patient_folder_id:
        try:
            get_folder_by_id(patient_folder_id)
        except GirderError:
            patient_folder_id = None
    
    if not patient_folder_id:
        patient_folder = find_folder(patient_id, center_folder_id)
        if not patient_folder:
            raise ValueError(
                f"Patient '{patient_id}' not found in Girder under '{center_girder_name}'. "
                f"Please run create_girder_schema.py first."
            )
        patient_folder_id = patient_folder['_id']
    
    # Step 3: Find Visit folder
    visit_folder_id = file_info.get('visit_girder_folder_id')
    
    if visit_folder_id:
        try:
            get_folder_by_id(visit_folder_id)
        except GirderError:
            visit_folder_id = None
    
    if not visit_folder_id:
        visit_folder = find_folder(visit_name, patient_folder_id)
        if not visit_folder:
            raise ValueError(
                f"Visit '{visit_name}' not found in Girder under patient '{patient_id}'. "
                f"Please run create_girder_schema.py first."
            )
        visit_folder_id = visit_folder['_id']
    
    # Step 4: Find Document Type folder (this is where we upload the file)
    doc_folder_id = file_info.get('doc_girder_folder_id')
    
    if doc_folder_id:
        try:
            get_folder_by_id(doc_folder_id)
        except GirderError:
            doc_folder_id = None
    
    if not doc_folder_id:
        doc_folder = find_folder(document_name, visit_folder_id)
        if not doc_folder:
            raise ValueError(
                f"Document type '{document_name}' not found in Girder under visit '{visit_name}'. "
                f"Please run create_girder_schema.py first."
            )
        doc_folder_id = doc_folder['_id']
    
    # Build folder path string for logging
    folder_path = f"{center_girder_name}/{patient_id}/{visit_name}/{document_name}"
    
    return doc_folder_id, folder_path


def sync_single_file(
    file_info: Dict,
    root_folder_id: str,
    db: Database
) -> Tuple[bool, str, Optional[str]]:
    """
    Sync a single file to Girder.
    
    WHAT IT DOES:
    1. Validates file exists on disk
    2. Finds correct Girder folder path
    3. Uploads file to Girder
    4. Marks file as synced in database
    
    Args:
        file_info: Dictionary with file information
        root_folder_id: Root folder ID in Girder
        db: Database instance
        
    Returns:
        Tuple of (success: bool, message: str, girder_file_id: Optional[str])
    """
    file_id = file_info['id']
    filename = file_info['filename']
    file_path = Path(file_info['file_path'])
    
    try:
        # Step 1: Check if file exists on disk
        if not file_path.exists():
            error_msg = f"File not found on disk: {file_path}"
            logger.error(f"   ❌ File {file_id} ({filename}): {error_msg}")
            return False, error_msg, None
        
        # Step 2: Find Girder folder path
        try:
            girder_folder_id, folder_path = find_girder_folder_path(file_info, root_folder_id)
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"   ❌ File {file_id} ({filename}): {error_msg}")
            return False, error_msg, None
        
        # Step 3: Read file from disk
        logger.info(f"   📤 Uploading: {filename} → {folder_path}")
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Step 4: Upload to Girder
        try:
            girder_file = upload_file(file_data, girder_folder_id, filename)
            girder_file_id = girder_file['_id']
            
            # Step 5: Mark as synced in database
            db.mark_file_synced(file_id, girder_file_id)
            
            success_msg = f"Successfully synced to {folder_path}"
            logger.info(f"   ✅ File {file_id} ({filename}): {success_msg}")
            return True, success_msg, girder_file_id
            
        except GirderError as e:
            error_msg = f"Failed to upload to Girder: {str(e)}"
            logger.error(f"   ❌ File {file_id} ({filename}): {error_msg}")
            return False, error_msg, None
            
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"   ❌ File {file_id} ({filename}): {error_msg}", exc_info=True)
        return False, error_msg, None


def extract_and_sync_files(root_folder_id: str) -> Dict:
    """
    Main function: Extract all unsynced files and sync them to Girder.
    
    WHAT IT DOES:
    1. Gets all unsynced files from database
    2. For each file, syncs it to Girder
    3. Returns summary of results
    
    Args:
        root_folder_id: Root folder ID in Girder
        
    Returns:
        Dictionary with sync results:
        {
            "total_files": int,
            "synced": int,
            "failed": int,
            "details": List[Dict]
        }
    """
    logger.info("=" * 60)
    logger.info("Starting Extract & Sync Process")
    logger.info("=" * 60)
    
    # Initialize database
    db = Database()
    
    # Step 1: Extract unsynced files
    unsynced_files = get_unsynced_files(db)
    
    if not unsynced_files:
        logger.info("✅ No files to sync. All files are already synced!")
        return {
            "total_files": 0,
            "synced": 0,
            "failed": 0,
            "details": []
        }
    
    logger.info(f"\n🔄 Syncing {len(unsynced_files)} file(s)...")
    logger.info("-" * 60)
    
    # Step 2: Sync each file
    results = {
        "total_files": len(unsynced_files),
        "synced": 0,
        "failed": 0,
        "details": []
    }
    
    for file_info in unsynced_files:
        file_id = file_info['id']
        filename = file_info['filename']
        
        success, message, girder_file_id = sync_single_file(
            file_info,
            root_folder_id,
            db
        )
        
        if success:
            results["synced"] += 1
        else:
            results["failed"] += 1
        
        results["details"].append({
            "file_id": file_id,
            "filename": filename,
            "success": success,
            "message": message,
            "girder_file_id": girder_file_id
        })
    
    # Step 3: Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Sync Summary")
    logger.info("=" * 60)
    logger.info(f"Total files: {results['total_files']}")
    logger.info(f"✅ Synced: {results['synced']}")
    logger.info(f"❌ Failed: {results['failed']}")
    
    if results['failed'] > 0:
        logger.info("\nFailed files:")
        for detail in results['details']:
            if not detail['success']:
                logger.info(f"  - {detail['filename']}: {detail['message']}")
    
    logger.info("=" * 60)
    
    return results


def get_unsynced_files_count() -> int:
    """
    Get count of unsynced files (useful for Airflow to check if sync is needed).
    
    Returns:
        Number of unsynced files
    """
    db = Database()
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM files WHERE synced_to_girder = 0")
    count = cursor.fetchone()[0]
    conn.close()
    return count


if __name__ == "__main__":
    """
    Main entry point when script is run directly.
    
    Usage:
        python sync/extract_sync.py
    """
    import os
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get root folder ID from environment variable
    root_folder_id = os.getenv("GIRDER_ROOT_FOLDER_ID")
    
    if not root_folder_id:
        logger.error("❌ GIRDER_ROOT_FOLDER_ID not set in environment variables!")
        logger.error("   Please set it in your .env file or export it:")
        logger.error("   export GIRDER_ROOT_FOLDER_ID=your_folder_id_here")
        sys.exit(1)
    
    logger.info(f"📁 Root folder ID: {root_folder_id}")
    
    # Run extract and sync
    try:
        results = extract_and_sync_files(root_folder_id)
        
        # Exit with error code if any files failed
        if results['failed'] > 0:
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
