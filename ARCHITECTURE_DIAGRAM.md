# REDCap-Girder Integration POC - Architecture Diagram

## System Architecture

```mermaid
graph TB
    subgraph RedCapMimic["REDCap Mimic System"]
        UI["REDCap Mimic UI<br/>http://localhost:8000/redcap-mimic"]
        DB[("SQLite Database<br/>redcap_mimic.db")]
        LocalFS["Local File Storage<br/>uploads/"]
    end
    
    subgraph FastAPIGateway["FastAPI Gateway"]
        API["FastAPI Server<br/>Port 8000"]
        Webhook["/redcap/webhook<br/>Metadata Handler"]
        Upload["/api/upload<br/>File Upload"]
        Sync["/api/sync-to-girder<br/>Sync Handler"]
        Schema["create_girder_schema.py<br/>Schema Creator"]
    end
    
    subgraph GirderInstance["Girder Instance"]
        GirderAPI["Girder API<br/>Port 8080"]
        GirderFS["Girder File Storage"]
        Folders["Folder Structure<br/>CHU_Center/Patient/Visit/DocType/"]
    end
    
    UI -->|"1. Upload File"| Upload
    Upload -->|"2. Save to Disk"| LocalFS
    Upload -->|"3. Store Metadata"| DB
    UI -->|"4. Click Sync"| Sync
    Sync -->|"5. Read File"| LocalFS
    Sync -->|"6. Lookup Folder ID"| DB
    Sync -->|"7. Upload to Girder"| GirderAPI
    GirderAPI -->|"8. Store File"| GirderFS
    Sync -->|"9. Mark as Synced"| DB
    
    Schema -->|"Create Folders"| GirderAPI
    Schema -->|"Store Folder IDs"| DB
    GirderAPI -->|"Return Folder IDs"| Schema
    
    Webhook -->|"Lookup Folder"| DB
    Webhook -->|"Return Folder ID"| UI
    
    style UI fill:#667eea,color:#fff
    style API fill:#28a745,color:#fff
    style GirderAPI fill:#17a2b8,color:#fff
    style DB fill:#ffc107,color:#000
    style LocalFS fill:#ffc107,color:#000
    style GirderFS fill:#17a2b8,color:#fff
```

## Data Flow - Upload & Sync Workflow

```mermaid
sequenceDiagram
    participant User
    participant UI as REDCap Mimic UI
    participant API as FastAPI
    participant DB as SQLite DB
    participant Local as Local Disk
    participant Girder as Girder API
    
    Note over User,Girder: Workflow 1: Upload → Local → Sync
    
    User->>UI: 1. Click "Upload" button
    UI->>API: 2. POST /api/upload (file)
    API->>Local: 3. Save file to disk
    API->>DB: 4. Store file metadata
    API-->>UI: 5. Return file_id
    UI->>UI: 6. Show "Pending" status
    
    User->>UI: 7. Click "Sync with Girder"
    UI->>API: 8. POST /api/sync-to-girder (file_id)
    API->>DB: 9. Lookup folder_id
    API->>Local: 10. Read file from disk
    API->>Girder: 11. Upload file (chunked)
    Girder-->>API: 12. Return girder_file_id
    API->>DB: 13. Mark as synced
    API-->>UI: 14. Return success
    UI->>UI: 15. Show "Synced" status
```

## Folder Structure in Girder

```mermaid
graph TD
    Root["ROOT_FOLDER"]
    
    Root --> CHU1["CHU_Bordeaux"]
    Root --> CHU2["CHU_Paris"]
    Root --> CHU3["CHU_Toulouse"]
    
    CHU1 --> P1["Patient_001"]
    CHU1 --> P2["Patient_002"]
    
    P1 --> V1["Inclusion M0"]
    P1 --> V2["Preinclusion M-6"]
    P1 --> V3["Visite M12"]
    P1 --> V4["Visite M24"]
    
    V1 --> D1["Bilan Biologique"]
    V1 --> D2["Consentement_Eclaire"]
    V1 --> D3["Dosage des β HCG"]
    
    D1 --> F1["File1.dcm"]
    D1 --> F2["File2.zip"]
    
    style Root fill:#667eea,color:#fff
    style CHU1 fill:#28a745,color:#fff
    style CHU2 fill:#28a745,color:#fff
    style CHU3 fill:#28a745,color:#fff
    style P1 fill:#17a2b8,color:#fff
    style V1 fill:#ffc107,color:#000
    style D1 fill:#fd7e14,color:#fff
    style F1 fill:#6c757d,color:#fff
```

## Component Details

```mermaid
graph LR
    subgraph RedCapMimic2["REDCap Mimic"]
        A1["Centers Table"]
        A2["Patients Table"]
        A3["Visits Table"]
        A4["Document Types Table"]
        A5["Files Table"]
    end
    
    subgraph FastAPIEndpoints["FastAPI Endpoints"]
        B1["/redcap/webhook<br/>Metadata → Folder ID"]
        B2["/api/upload<br/>File → Local Disk"]
        B3["/api/sync-to-girder<br/>Local → Girder"]
        B4["/api/structure<br/>Get Tree View"]
        B5["/api/files<br/>List Files"]
    end
    
    subgraph GirderClient["Girder Client Functions"]
        C1["get_document_folder_id<br/>Database Lookup"]
        C2["upload_file<br/>Chunked Upload"]
        C3["get_or_create_folder<br/>Folder Management"]
        C4["get_folder_by_id<br/>Validation"]
    end
    
    A5 -->|"Query"| B3
    B3 -->|"Lookup"| C1
    B3 -->|"Upload"| C2
    C1 -->|"Fast Query"| A4
    C2 -->|"API Call"| Girder["Girder API"]
```

## Security Architecture

```mermaid
graph TB
    User["User/CRA"]
    REDCap["REDCap System"]
    
    subgraph SecureGateway["Secure Gateway"]
        FastAPI["FastAPI Server<br/>Has Girder Credentials"]
        DB[("Database<br/>Folder IDs")]
    end
    
    subgraph GirderInstance2["Girder Instance"]
        Girder["Girder API<br/>Port 8080"]
        Storage["File Storage"]
    end
    
    User -->|"1. Fill Form"| REDCap
    REDCap -->|"2. Webhook POST<br/>Metadata Only"| FastAPI
    FastAPI -->|"3. Lookup Folder ID"| DB
    FastAPI -->|"4. Return Folder ID"| REDCap
    
    User -->|"5. Upload File"| FastAPI
    FastAPI -->|"6. Validate"| DB
    FastAPI -->|"7. Upload to Girder<br/>Using API Key"| Girder
    Girder -->|"8. Store File"| Storage
    
    Note1["Users never have<br/>direct Girder access"]
    Note2["Only FastAPI has<br/>Girder credentials"]
    
    style FastAPI fill:#28a745,color:#fff
    style Girder fill:#17a2b8,color:#fff
    style Note1 fill:#ffc107,color:#000
    style Note2 fill:#ffc107,color:#000
```

## Production Architecture (Future)

```mermaid
graph TB
    subgraph RedCapProduction["REDCap Production"]
        REDCap["REDCap Server<br/>Real System"]
        REDCapAPI["REDCap API<br/>Metadata & Forms"]
    end
    
    subgraph IntegrationLayer["Integration Layer"]
        FastAPI["FastAPI Gateway<br/>Secure Endpoint"]
        Queue["Message Queue<br/>Optional"]
        DB[("PostgreSQL<br/>Production DB")]
    end
    
    subgraph GirderProduction["Girder Production"]
        GirderAPI["Girder API"]
        GirderStorage["Distributed Storage"]
    end
    
    REDCap -->|"Webhook"| FastAPI
    REDCapAPI -->|"Query Structure"| FastAPI
    FastAPI -->|"Lookup"| DB
    FastAPI -->|"Upload Files"| GirderAPI
    GirderAPI -->|"Store"| GirderStorage
    
    Queue -.->|"Async Processing"| FastAPI
    
    style REDCap fill:#667eea,color:#fff
    style FastAPI fill:#28a745,color:#fff
    style GirderAPI fill:#17a2b8,color:#fff
```

## Key Features

1. **Pre-populated Schema**: Folder structure created once in Girder
2. **Fast Lookups**: Database queries instead of API calls
3. **Secure Gateway**: Only FastAPI has Girder credentials
4. **Chunked Uploads**: Handles large files (ZIP, DICOM)
5. **Dual Workflow**: Upload→Sync (POC) and Direct Upload (Production-ready)
