#!/usr/bin/env python3
"""
Script to create Girder folder structure matching REDCap mimic database schema.

WHAT THIS SCRIPT DOES:
=====================
1. Reads the structure from REDCap mimic SQLite database:
   - Centers (hospitals: Bordeaux, Paris, Toulouse)
   - Patients (2 per center)
   - Visits (4 per patient: M0, M-6, M12, M24)
   - Document Types (Bilan Biologique, Consentement_Eclaire, etc.)

2. Creates matching folder structure in Girder:
   ROOT_FOLDER/
   ├── CHU_Bordeaux/
   │   ├── Patient_001/
   │   │   ├── Inclusion M0/
   │   │   │   ├── Bilan Biologique/
   │   │   │   ├── Consentement_Eclaire/
   │   │   │   └── Dosage des β HCG/
   │   │   ├── Preinclusion M-6/
   │   │   │   └── (document types...)
   │   │   └── (other visits...)
   │   └── Patient_002/
   │       └── (same structure)
   └── CHU_Paris/
       └── (same structure)

3. Stores Girder folder IDs back in SQLite database
   - This allows us to track what's already synced
   - Prevents creating duplicate folders

HOW IT WORKS WITH REAL REDCAP:
==============================
In production, instead of reading from SQLite, you would:
1. Use REDCap API to query project structure:
   - GET /api/project_info.php (get project metadata)
   - GET /api/metadata.php (get forms/fields)
   - GET /api/events.php (get events/visits if longitudinal)
   
2. Parse REDCap API responses to extract:
   - Forms (equivalent to document types)
   - Events/Visits (if longitudinal study)
   - Records (patients)
   
3. Create matching folder structure in Girder
   - Same logic as this script, but data source is REDCap API

This script is the "mimic" version - it reads from SQLite instead of REDCap API.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Database
from girder_client import (
    get_or_create_folder,
    find_folder,
    GirderError
)
import logging
import sqlite3

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_girder_schema(root_folder_id: str):
    """
    Main function that creates the complete Girder schema.
    
    Args:
        root_folder_id: The ID of the root folder in Girder where we'll create everything
    """
    # Step 1: Initialize database connection
    # This connects to our SQLite database (redcap_mimic.db)
    logger.info("=" * 60)
    logger.info("Starting Girder Schema Creation")
    logger.info("=" * 60)
    
    db = Database()
    
    # Step 2: Get the complete structure from SQLite database
    # This returns a nested structure: centers -> patients -> visits -> document_types
    logger.info("\n📖 Reading structure from REDCap mimic database...")
    structure = db.get_full_structure()
    
    logger.info(f"Found {len(structure)} centers in database")
    
    # Step 3: Process each center (hospital)
    for center in structure:
        center_code = center['code']  # e.g., "Bordeaux"
        center_name = center['name']   # e.g., "CHU Bordeaux"
        center_girder_name = f"CHU_{center_code}"  # e.g., "CHU_Bordeaux"
        
        logger.info(f"\n🏥 Processing Center: {center_name} ({center_code})")
        
        # Step 3a: Create or find the center folder in Girder
        # This creates a folder like "CHU_Bordeaux" under the root folder
        try:
            center_folder = get_or_create_folder(
                name=center_girder_name,
                parent_id=root_folder_id,
                public=True
            )
            center_girder_id = center_folder['_id']
            logger.info(f"   ✅ Center folder '{center_girder_name}' ready (ID: {center_girder_id[:8]}...)")
            
            # Step 3b: Update database with Girder folder ID (if not already set)
            # This stores the Girder folder ID so we know it's synced
            if not center.get('girder_folder_id'):
                conn_db = sqlite3.connect(db.db_path)
                cursor = conn_db.cursor()
                cursor.execute(
                    "UPDATE centers SET girder_folder_id = ? WHERE id = ?",
                    (center_girder_id, center['id'])
                )
                conn_db.commit()
                conn_db.close()
                logger.info(f"   💾 Saved Girder folder ID to database")
            
        except GirderError as e:
            logger.error(f"   ❌ Failed to create center folder: {str(e)}")
            continue  # Skip this center if we can't create it
        
        # Step 4: Process each patient under this center
        for patient in center.get('patients', []):
            patient_id = patient['patient_id']  # e.g., "Patient_001"
            
            logger.info(f"\n   👤 Processing Patient: {patient_id}")
            
            # Step 4a: Create or find the patient folder in Girder
            # This creates a folder like "Patient_001" under "CHU_Bordeaux"
            try:
                patient_folder = get_or_create_folder(
                    name=patient_id,
                    parent_id=center_girder_id,
                    public=True
                )
                patient_girder_id = patient_folder['_id']
                logger.info(f"      ✅ Patient folder '{patient_id}' ready (ID: {patient_girder_id[:8]}...)")
                
                # Step 4b: Update database with Girder folder ID
                if not patient.get('girder_folder_id'):
                    conn_db = sqlite3.connect(db.db_path)
                    cursor = conn_db.cursor()
                    cursor.execute(
                        "UPDATE patients SET girder_folder_id = ? WHERE id = ?",
                        (patient_girder_id, patient['id'])
                    )
                    conn_db.commit()
                    conn_db.close()
                    logger.info(f"      💾 Saved Girder folder ID to database")
                
            except GirderError as e:
                logger.error(f"      ❌ Failed to create patient folder: {str(e)}")
                continue  # Skip this patient if we can't create it
            
            # Step 5: Process each visit under this patient
            for visit in patient.get('visits', []):
                visit_name = visit['visit_name']  # e.g., "Inclusion M0"
                visit_code = visit['visit_code']  # e.g., "M0"
                
                logger.info(f"\n      📅 Processing Visit: {visit_name} ({visit_code})")
                
                # Step 5a: Create or find the visit folder in Girder
                # This creates a folder like "Inclusion M0" under "Patient_001"
                try:
                    visit_folder = get_or_create_folder(
                        name=visit_name,
                        parent_id=patient_girder_id,
                        public=True
                    )
                    visit_girder_id = visit_folder['_id']
                    logger.info(f"         ✅ Visit folder '{visit_name}' ready (ID: {visit_girder_id[:8]}...)")
                    
                    # Step 5b: Update database with Girder folder ID
                    if not visit.get('girder_folder_id'):
                        conn_db = sqlite3.connect(db.db_path)
                        cursor = conn_db.cursor()
                        cursor.execute(
                            "UPDATE visits SET girder_folder_id = ? WHERE id = ?",
                            (visit_girder_id, visit['id'])
                        )
                        conn_db.commit()
                        conn_db.close()
                        logger.info(f"         💾 Saved Girder folder ID to database")
                    
                except GirderError as e:
                    logger.error(f"         ❌ Failed to create visit folder: {str(e)}")
                    continue  # Skip this visit if we can't create it
                
                # Step 6: Process each document type under this visit
                for doc_type in visit.get('document_types', []):
                    doc_name = doc_type['document_name']  # e.g., "Bilan Biologique"
                    doc_code = doc_type['document_code']  # e.g., "bilan_biologique"
                    
                    logger.info(f"            📄 Processing Document Type: {doc_name}")
                    
                    # Step 6a: Create or find the document type folder in Girder
                    # This creates a folder like "Bilan Biologique" under "Inclusion M0"
                    try:
                        doc_folder = get_or_create_folder(
                            name=doc_name,
                            parent_id=visit_girder_id,
                            public=True
                        )
                        doc_girder_id = doc_folder['_id']
                        logger.info(f"               ✅ Document folder '{doc_name}' ready (ID: {doc_girder_id[:8]}...)")
                        
                        # Step 6b: Update database with Girder folder ID
                        if not doc_type.get('girder_folder_id'):
                            conn_db = sqlite3.connect(db.db_path)
                            cursor = conn_db.cursor()
                            cursor.execute(
                                "UPDATE document_types SET girder_folder_id = ? WHERE id = ?",
                                (doc_girder_id, doc_type['id'])
                            )
                            conn_db.commit()
                            conn_db.close()
                            logger.info(f"               💾 Saved Girder folder ID to database")
                        
                    except GirderError as e:
                        logger.error(f"               ❌ Failed to create document folder: {str(e)}")
                        continue  # Skip this document type if we can't create it
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Schema creation completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    """
    Main entry point when script is run directly.
    
    Usage:
        python scripts/create_girder_schema.py
    """
    import os
    from dotenv import load_dotenv
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get root folder ID from environment variable
    # This is the folder in Girder where all CHU folders will be created
    root_folder_id = os.getenv("GIRDER_ROOT_FOLDER_ID")
    
    if not root_folder_id:
        logger.error("❌ GIRDER_ROOT_FOLDER_ID not set in environment variables!")
        logger.error("   Please set it in your .env file or export it:")
        logger.error("   export GIRDER_ROOT_FOLDER_ID=your_folder_id_here")
        sys.exit(1)
    
    logger.info(f"📁 Root folder ID: {root_folder_id}")
    
    # Run the schema creation
    try:
        create_girder_schema(root_folder_id)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
