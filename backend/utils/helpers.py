from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def ensure_upload_dirs():
    """Ensure upload directories exist"""
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # Create subdirs for users (will be created dynamically)
    logger.info("Upload directories ensured")

def validate_file_type(filename: str, allowed_extensions: str) -> bool:
    """Validate file extension"""
    ext = Path(filename).suffix.lower().lstrip('.')
    allowed_list = [e.strip().lower() for e in allowed_extensions.split(",")]
    return ext in allowed_list

def get_file_size_mb(file_path: str) -> float:
    """Get file size in MB"""
    return Path(file_path).stat().st_size / (1024 * 1024)
