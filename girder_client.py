import requests
import os
import logging
import time
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GIRDER_API_URL = os.getenv("GIRDER_API_URL")
API_KEY = os.getenv("GIRDER_API_KEY")

if not GIRDER_API_URL:
    raise RuntimeError("GIRDER_API_URL is not set")

if not API_KEY:
    raise RuntimeError("GIRDER_API_KEY is not set")

# Exchange API key for token
def get_girder_token(api_key, api_url):
    """
    Exchange API key for a Girder authentication token.
    
    Args:
        api_key: The API key string
        api_url: Base Girder API URL
        
    Returns:
        Token string to use in Girder-Token header
    """
    try:
        logger.info("Exchanging API key for authentication token...")
        # Send as form data (application/x-www-form-urlencoded)
        r = requests.post(
            f"{api_url}/api_key/token",
            data={"key": api_key}  # Use 'data' for form data
        )
        r.raise_for_status()
        response = r.json()
        token = response['authToken']['token']
        logger.info("Successfully obtained authentication token")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to exchange API key for token: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise RuntimeError(f"Authentication failed: {str(e)}")

# Get token from API key
GIRDER_TOKEN = get_girder_token(API_KEY, GIRDER_API_URL)
HEADERS = {"Girder-Token": GIRDER_TOKEN}

logger.info(f"Initialized Girder client with API URL: {GIRDER_API_URL}")


class GirderError(Exception):
    """Custom exception for Girder API errors"""
    pass


def find_folder(name, parent_id):
    """
    Find a folder by name within a parent folder.
    
    Args:
        name: Name of the folder to find
        parent_id: ID of the parent folder
        
    Returns:
        Folder dict if found, None otherwise
        
    Raises:
        GirderError: If API request fails
    """
    try:
        r = requests.get(
            f"{GIRDER_API_URL}/folder",
            headers=HEADERS,
            params={
                "parentId": parent_id,
                "parentType": "folder",
                "name": name,
                "limit": 1
            }
        )
        r.raise_for_status()

        result = r.json()

        # Girder may return {"data": [...]} or directly [...]
        if isinstance(result, dict):
            folders = result.get("data", [])
        else:
            folders = result

        folder = folders[0] if folders else None
        if folder:
            logger.info(f"Found folder '{name}' with ID: {folder.get('_id')}")
        else:
            logger.debug(f"Folder '{name}' not found in parent {parent_id}")
        
        return folder
    except requests.exceptions.RequestException as e:
        logger.error(f"Error finding folder '{name}': {str(e)}")
        raise GirderError(f"Failed to find folder: {str(e)}")


def create_folder(name, parent_id, public=True):
    """
    Create a new folder in Girder.
    
    Args:
        name: Name of the folder to create
        parent_id: ID of the parent folder
        public: Whether the folder should be publicly accessible (default: True)
        
    Returns:
        Created folder dict
        
    Raises:
        GirderError: If API request fails
    """
    try:
        logger.info(f"Creating folder '{name}' in parent {parent_id} (public={public})")
        r = requests.post(
            f"{GIRDER_API_URL}/folder",
            headers=HEADERS,
            data={
                "name": name,
                "parentId": parent_id,
                "parentType": "folder",
                "public": str(public).lower()  # Convert boolean to string
            }
        )
        r.raise_for_status()
        folder = r.json()
        logger.info(f"Created folder '{name}' with ID: {folder.get('_id')}")
        return folder
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating folder '{name}': {str(e)}")
        raise GirderError(f"Failed to create folder: {str(e)}")


def get_or_create_folder(name, parent_id, public=True):
    """
    Get an existing folder or create it if it doesn't exist.
    
    Args:
        name: Name of the folder
        parent_id: ID of the parent folder
        public: Whether the folder should be publicly accessible (default: True)
        
    Returns:
        Folder dict (existing or newly created)
        
    Raises:
        GirderError: If API request fails
    """
    folder = find_folder(name, parent_id)
    if not folder:
        folder = create_folder(name, parent_id, public=public)
    return folder


def set_metadata(folder_id, metadata):
    """
    Set metadata on a folder. This will merge with existing metadata.
    
    Args:
        folder_id: ID of the folder
        metadata: Dict of metadata to set
        
    Raises:
        GirderError: If API request fails
    """
    try:
        logger.info(f"Setting metadata on folder {folder_id}")
        r = requests.put(
            f"{GIRDER_API_URL}/folder/{folder_id}/metadata",
            headers=HEADERS,
            json=metadata
        )
        r.raise_for_status()
        logger.info(f"Successfully set metadata on folder {folder_id}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error setting metadata on folder {folder_id}: {str(e)}")
        raise GirderError(f"Failed to set metadata: {str(e)}")


def get_folder_by_id(folder_id):
    """
    Get folder details by ID.
    
    Args:
        folder_id: ID of the folder
        
    Returns:
        Folder dict
        
    Raises:
        GirderError: If API request fails
    """
    try:
        r = requests.get(
            f"{GIRDER_API_URL}/folder/{folder_id}",
            headers=HEADERS
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting folder {folder_id}: {str(e)}")
        raise GirderError(f"Failed to get folder: {str(e)}")


def upload_file(file_path, folder_id, file_name=None):
    """
    Upload a file to a Girder folder.
    
    Args:
        file_path: Path to local file, bytes data, or file-like object
        folder_id: ID of the folder to upload to
        file_name: Name for the file (defaults to filename from path)
        
    Returns:
        Created file dict
        
    Raises:
        GirderError: If API request fails
    """
    import os
    import io
    from pathlib import Path
    
    # Handle file path or bytes
    if isinstance(file_path, (str, Path)):
        file_path = Path(file_path)
        file_name = file_name or file_path.name
        file_size = file_path.stat().st_size
        with open(file_path, 'rb') as f:
            file_data = f.read()
    elif isinstance(file_path, bytes):
        # Assume bytes data
        file_data = file_path
        file_size = len(file_data)
        if not file_name:
            raise ValueError("file_name is required when file_path is bytes")
    else:
        # Assume file-like object
        file_data = file_path.read()
        file_size = len(file_data)
        file_name = file_name or "uploaded_file"
    
    # Detect MIME type from extension
    mime_type = "application/octet-stream"
    if file_name:
        ext = Path(file_name).suffix.lower()
        mime_map = {
            '.dcm': 'application/dicom',
            '.dicom': 'application/dicom',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.7z': 'application/x-7z-compressed',
            '.tar': 'application/x-tar',
            '.gz': 'application/gzip',
        }
        mime_type = mime_map.get(ext, 'application/octet-stream')
    
    try:
        logger.info(f"Initializing upload for {file_name} ({file_size} bytes) to folder {folder_id}")
        
        # Step 1: Initialize upload
        r = requests.post(
            f"{GIRDER_API_URL}/file",
            headers=HEADERS,
            params={
                "parentType": "folder",
                "parentId": folder_id,
                "name": file_name,
                "size": file_size,
                "mimeType": mime_type
            }
        )
        r.raise_for_status()
        upload = r.json()
        upload_id = upload["_id"]
        
        # Step 2: Upload file data in chunks (for large files)
        # Use 10MB chunks to avoid hitting server limits
        CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
        
        if file_size <= CHUNK_SIZE:
            # Small file - upload in one chunk
            logger.info(f"Uploading file data for {file_name} (single chunk)")
            r = requests.post(
                f"{GIRDER_API_URL}/file/chunk",
                headers=HEADERS,
                params={
                    "uploadId": upload_id,
                    "offset": 0
                },
                data=file_data
            )
            r.raise_for_status()
            file_result = r.json()
        else:
            # Large file - upload in chunks
            logger.info(f"Uploading large file {file_name} in chunks (chunk size: {CHUNK_SIZE / (1024*1024):.1f} MB)")
            offset = 0
            file_io = io.BytesIO(file_data) if isinstance(file_data, bytes) else file_data
            
            # Ensure we start from the beginning
            if hasattr(file_io, 'seek'):
                file_io.seek(0)
            
            file_result = None
            
            while offset < file_size:
                # Read chunk
                chunk_size = min(CHUNK_SIZE, file_size - offset)
                chunk_data = file_io.read(chunk_size)
                
                if not chunk_data:
                    break
                
                percent = (offset * 100) // file_size if file_size > 0 else 0
                logger.info(f"Uploading chunk: {offset}/{file_size} bytes ({percent}%)")
                
                # Upload chunk with timeout for large files
                r = requests.post(
                    f"{GIRDER_API_URL}/file/chunk",
                    headers=HEADERS,
                    params={
                        "uploadId": upload_id,
                        "offset": offset
                    },
                    data=chunk_data,
                    timeout=300  # 5 minute timeout per chunk
                )
                r.raise_for_status()
                
                # Check response
                result = r.json()
                
                # Update offset from server response (if provided)
                if 'received' in result:
                    offset = result['received']
                else:
                    # Fallback: update offset manually
                    offset += len(chunk_data)
                
                # Check if this is the final chunk (offset >= file_size)
                if offset >= file_size:
                    # This should be the file document
                    if '_id' in result and 'size' in result:
                        file_result = result
                        logger.info(f"Upload complete: {file_name} (all chunks uploaded)")
                        break
                    else:
                        # Sometimes need to wait a moment for server to finalize
                        logger.info("Final chunk uploaded, waiting for server to finalize...")
                        time.sleep(0.5)
                        # Try to get the file from the upload status
                        # The file should be available now
                        if '_id' in result:
                            file_result = result
                            break
                        else:
                            # Last resort: check if upload is complete by getting upload status
                            logger.warning("Checking upload status after final chunk...")
                            # Continue - the file should be available
                            break
                
                # Small delay to avoid overwhelming the server
                time.sleep(0.1)
            
            # Close file if it's a BytesIO
            if isinstance(file_io, io.BytesIO):
                file_io.close()
            
            # Verify upload completed
            if not file_result:
                raise GirderError(f"Upload did not complete. Last offset: {offset}, Expected: {file_size}. File may be incomplete in Girder.")
            
            # Double-check: verify the file size matches
            if file_result.get('size') != file_size:
                logger.warning(f"File size mismatch: expected {file_size}, got {file_result.get('size')}")
        
        logger.info(f"Successfully uploaded {file_name} with ID: {file_result.get('_id')}")
        return file_result
    except requests.exceptions.RequestException as e:
        logger.error(f"Error uploading file '{file_name}': {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise GirderError(f"Failed to upload file: {str(e)}")


def download_and_upload_file(file_url, folder_id, file_name):
    """
    Download a file from a URL and upload it to Girder.
    
    Args:
        file_url: URL to download file from
        folder_id: ID of the folder to upload to
        file_name: Name for the file in Girder
        
    Returns:
        Created file dict
        
    Raises:
        GirderError: If API request fails
    """
    try:
        logger.info(f"Downloading file from {file_url}")
        response = requests.get(file_url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Download to memory (for small files) or temp file (for large files)
        file_data = response.content
        logger.info(f"Downloaded {len(file_data)} bytes from {file_url}")
        
        return upload_file(file_data, folder_id, file_name)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading file from {file_url}: {str(e)}")
        raise GirderError(f"Failed to download and upload file: {str(e)}")


def extract_and_upload_zip(zip_data, folder_id, zip_name=None, extract_dicom=True):
    """
    Extract a ZIP archive and upload all files (or just DICOM files) to Girder.
    
    Args:
        zip_data: ZIP file data as bytes
        folder_id: ID of the folder to upload extracted files to
        zip_name: Name of the ZIP file (for logging)
        extract_dicom: If True, only extract DICOM files. If False, extract all files.
        
    Returns:
        List of uploaded file dicts with 'name', 'id', 'size'
        
    Raises:
        GirderError: If extraction or upload fails
    """
    import zipfile
    import io
    from pathlib import Path
    
    zip_name = zip_name or "archive.zip"
    uploaded_files = []
    
    try:
        logger.info(f"Extracting ZIP archive: {zip_name} ({len(zip_data)} bytes)")
        
        # Open ZIP from bytes
        zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
        
        # Get list of files in ZIP
        file_list = zip_file.namelist()
        logger.info(f"Found {len(file_list)} file(s) in ZIP archive")
        
        # Filter for DICOM files if requested
        if extract_dicom:
            dicom_extensions = {'.dcm', '.dicom'}
            original_count = len(file_list)
            file_list = [
                f for f in file_list 
                if Path(f).suffix.lower() in dicom_extensions and not f.endswith('/')
            ]
            logger.info(f"Filtered to {len(file_list)} DICOM file(s) from {original_count} total file(s)")
        
        if not file_list:
            logger.warning(f"No files found in ZIP archive {zip_name} (or no DICOM files if extract_dicom=True)")
            return []
        
        # Extract and upload each file
        for file_path in file_list:
            try:
                # Get file data from ZIP
                file_data = zip_file.read(file_path)
                
                # Use the filename from the ZIP (preserve directory structure in name)
                file_name = Path(file_path).name
                if not file_name:
                    # Skip directories
                    continue
                
                logger.info(f"Extracting and uploading: {file_name} ({len(file_data)} bytes)")
                
                # Upload to Girder
                file_result = upload_file(file_data, folder_id, file_name)
                
                uploaded_files.append({
                    "name": file_name,
                    "original_path": file_path,
                    "id": file_result.get("_id"),
                    "size": file_result.get("size", len(file_data))
                })
                
            except Exception as e:
                logger.error(f"Failed to extract/upload {file_path} from ZIP: {str(e)}")
                # Continue with other files
                continue
        
        zip_file.close()
        logger.info(f"Successfully extracted and uploaded {len(uploaded_files)} file(s) from ZIP")
        
        return uploaded_files
        
    except zipfile.BadZipFile:
        logger.error(f"Invalid ZIP file: {zip_name}")
        raise GirderError(f"Invalid ZIP file format: {zip_name}")
    except Exception as e:
        logger.error(f"Error extracting ZIP {zip_name}: {str(e)}")
        raise GirderError(f"Failed to extract ZIP archive: {str(e)}")


def set_folder_access(folder_id, public=True, access_list=None):
    """
    Set access permissions on a folder.
    
    Args:
        folder_id: ID of the folder
        public: Whether the folder should be publicly accessible
        access_list: Optional access control list (dict mapping user/group IDs to permission levels)
        
    Returns:
        Updated folder dict
        
    Raises:
        GirderError: If API request fails
    """
    try:
        logger.info(f"Setting folder access for {folder_id} (public={public})")
        params = {
            "public": str(public).lower(),
            "recurse": "false"  # Don't apply to subfolders by default
        }
        
        data = {}
        if access_list:
            data["access"] = access_list
        
        r = requests.put(
            f"{GIRDER_API_URL}/folder/{folder_id}/access",
            headers=HEADERS,
            params=params,
            json=data if data else None
        )
        r.raise_for_status()
        folder = r.json()
        logger.info(f"Successfully set folder access for {folder_id}")
        return folder
    except requests.exceptions.RequestException as e:
        logger.error(f"Error setting folder access for {folder_id}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise GirderError(f"Failed to set folder access: {str(e)}")

