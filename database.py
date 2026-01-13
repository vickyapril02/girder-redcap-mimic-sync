import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "redcap_mimic.db"):
        self.db_path = db_path
        self.init_database()
        self.populate_initial_data()
    
    def init_database(self):
        """Initialize SQLite database with schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Centers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                girder_folder_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Patients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                center_id INTEGER NOT NULL,
                patient_id TEXT NOT NULL,
                girder_folder_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (center_id) REFERENCES centers(id),
                UNIQUE(center_id, patient_id)
            )
        """)
        
        # Visits table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                visit_name TEXT NOT NULL,
                visit_code TEXT NOT NULL,
                girder_folder_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                UNIQUE(patient_id, visit_code)
            )
        """)
        
        # Document types table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_id INTEGER NOT NULL,
                document_name TEXT NOT NULL,
                document_code TEXT NOT NULL,
                girder_folder_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (visit_id) REFERENCES visits(id),
                UNIQUE(visit_id, document_code)
            )
        """)
        
        # Files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                mime_type TEXT,
                girder_file_id TEXT,
                synced_to_girder BOOLEAN DEFAULT 0,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_type_id) REFERENCES document_types(id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def populate_initial_data(self):
        """Pre-populate database with hospitals, patients, visits, and document types"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if data already exists
        cursor.execute("SELECT COUNT(*) FROM centers")
        if cursor.fetchone()[0] > 0:
            conn.close()
            logger.info("Initial data already populated")
            return
        
        # Hospitals
        hospitals = [
            ("Bordeaux", "CHU Bordeaux"),
            ("Paris", "CHU Paris"),
            ("Toulouse", "CHU Toulouse")
        ]
        
        center_ids = {}
        for code, name in hospitals:
            cursor.execute("INSERT INTO centers (code, name) VALUES (?, ?)", (code, name))
            center_ids[code] = cursor.lastrowid
        
        # Patients (2 per hospital)
        patient_ids = {}
        for center_code, center_id in center_ids.items():
            for i in range(1, 3):
                patient_id_str = f"Patient_{i:03d}"
                cursor.execute(
                    "INSERT INTO patients (center_id, patient_id) VALUES (?, ?)",
                    (center_id, patient_id_str)
                )
                patient_ids[(center_code, patient_id_str)] = cursor.lastrowid
        
        # Visits (4 per patient)
        visit_mapping = {
            "Inclusion M0": "M0",
            "Preinclusion M-6": "M-6",
            "Visite M12": "M12",
            "Visite M24": "M24"
        }
        
        visit_ids = {}
        for (center_code, patient_id_str), patient_db_id in patient_ids.items():
            for visit_name, visit_code in visit_mapping.items():
                cursor.execute(
                    "INSERT INTO visits (patient_id, visit_name, visit_code) VALUES (?, ?, ?)",
                    (patient_db_id, visit_name, visit_code)
                )
                visit_ids[(patient_db_id, visit_code)] = cursor.lastrowid
        
        # Document types per visit
        document_types_config = {
            "M0": ["Bilan Biologique", "Consentement_Eclaire", "Dosage des β HCG"],
            "M-6": ["Bilan Biologique", "Consentement_Eclaire", "Dosage des β HCG", "ECG 12 derivations"],
            "M12": ["Bilan Biologique", "Consentement_Eclaire", "Dosage des β HCG"],
            "M24": ["Bilan Biologique", "Consentement_Eclaire", "Dosage des β HCG"]
        }
        
        for (patient_db_id, visit_code), visit_db_id in visit_ids.items():
            doc_types = document_types_config.get(visit_code, [])
            for doc_name in doc_types:
                doc_code = doc_name.lower().replace(" ", "_").replace("é", "e").replace("β", "beta")
                cursor.execute(
                    "INSERT INTO document_types (visit_id, document_name, document_code) VALUES (?, ?, ?)",
                    (visit_db_id, doc_name, doc_code)
                )
        
        conn.commit()
        conn.close()
        logger.info("Initial data populated successfully")
    
    def get_full_structure(self) -> List[Dict]:
        """Get complete structure for display"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all centers
        cursor.execute("SELECT * FROM centers ORDER BY code")
        centers = [dict(row) for row in cursor.fetchall()]
        
        result = []
        for center in centers:
            # Get patients for this center
            cursor.execute("""
                SELECT * FROM patients WHERE center_id = ? ORDER BY patient_id
            """, (center['id'],))
            patients = [dict(row) for row in cursor.fetchall()]
            
            center_data = {
                **center,
                'patients': []
            }
            
            for patient in patients:
                # Get visits for this patient
                cursor.execute("""
                    SELECT * FROM visits WHERE patient_id = ? ORDER BY visit_code
                """, (patient['id'],))
                visits = [dict(row) for row in cursor.fetchall()]
                
                patient_data = {
                    **patient,
                    'visits': []
                }
                
                for visit in visits:
                    # Get document types for this visit
                    cursor.execute("""
                        SELECT * FROM document_types WHERE visit_id = ? ORDER BY document_name
                    """, (visit['id'],))
                    document_types = [dict(row) for row in cursor.fetchall()]
                    
                    # Get files for each document type
                    for doc_type in document_types:
                        cursor.execute("""
                            SELECT * FROM files WHERE document_type_id = ? ORDER BY uploaded_at DESC
                        """, (doc_type['id'],))
                        doc_type['files'] = [dict(row) for row in cursor.fetchall()]
                    
                    visit_data = {
                        **visit,
                        'document_types': document_types
                    }
                    patient_data['visits'].append(visit_data)
                
                center_data['patients'].append(patient_data)
            
            result.append(center_data)
        
        conn.close()
        return result
    
    def get_document_type(self, document_type_id: int) -> Optional[Dict]:
        """Get document type with related info"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT dt.*, v.visit_name, v.visit_code, p.patient_id, p.id as patient_db_id,
                   c.code as center_code, c.name as center_name
            FROM document_types dt
            JOIN visits v ON dt.visit_id = v.id
            JOIN patients p ON v.patient_id = p.id
            JOIN centers c ON p.center_id = c.id
            WHERE dt.id = ?
        """, (document_type_id,))
        
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def create_file(self, document_type_id: int, filename: str, file_path: str,
                   file_size: int, mime_type: str) -> int:
        """Create file record"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO files (document_type_id, filename, file_path, file_size, mime_type)
            VALUES (?, ?, ?, ?, ?)
        """, (document_type_id, filename, file_path, file_size, mime_type))
        file_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return file_id
    
    def mark_file_synced(self, file_id: int, girder_file_id: str):
        """Mark file as synced to Girder"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE files SET synced_to_girder = 1, girder_file_id = ? WHERE id = ?
        """, (girder_file_id, file_id))
        conn.commit()
        conn.close()
    
    def get_file(self, file_id: int) -> Optional[Dict]:
        """Get file by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_file_with_path_info(self, file_id: int) -> Optional[Dict]:
        """Get file with full path information (center → patient → visit → document)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
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
            WHERE f.id = ?
        """, (file_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_document_folder_id(
        self, 
        center_code: str, 
        patient_id: str, 
        visit_name: str, 
        document_name: str
    ) -> Optional[str]:
        """
        Lookup Girder folder ID for a document type from database.
        Fast database lookup - no Girder API call needed!
        
        Args:
            center_code: Center code (e.g., "Bordeaux")
            patient_id: Patient ID (e.g., "Patient_001")
            visit_name: Visit name (e.g., "Inclusion M0")
            document_name: Document type name (e.g., "Bilan Biologique")
            
        Returns:
            Girder folder ID if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT dt.girder_folder_id
            FROM document_types dt
            JOIN visits v ON dt.visit_id = v.id
            JOIN patients p ON v.patient_id = p.id
            JOIN centers c ON p.center_id = c.id
            WHERE c.code = ?
              AND p.patient_id = ?
              AND v.visit_name = ?
              AND dt.document_name = ?
        """, (center_code, patient_id, visit_name, document_name))
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row['girder_folder_id']:
            return row['girder_folder_id']
        return None

