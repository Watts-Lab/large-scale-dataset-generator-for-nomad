#!/usr/bin/env python3
"""
Utility functions for uploading files to S3.

This module provides reusable S3 upload functionality for any files or directories
generated during the data generation process.

Usage:
  python s3_upload.py <local_path> <bucket_name> [s3_prefix] [aws_profile]

Examples:
  # Upload a single file
  python s3_upload.py data/pois.parquet my-bucket pois/

  # Upload a directory recursively
  python s3_upload.py data/parquet my-bucket simulation_data/

  # Use specific AWS profile
  python s3_upload.py data/logs my-bucket logs/ my-aws-profile
  
  # Use as a module in other scripts:
  from s3_upload import upload_to_s3, create_s3_uploader, S3IncrementalUploader
  upload_to_s3('data/parquet', 'my-bucket', 's3_prefix/', 'profile-name')
  
  # For incremental uploads (memory-efficient for large datasets):
  uploader = create_s3_uploader('my-bucket', 's3_prefix/', 'profile-name')
  uploader.upload_file('local/file.parquet')  # Upload immediately
  uploader.upload_and_delete('local/temp.parquet')  # Upload and remove local file
"""

import sys
import boto3
import shutil
from pathlib import Path


class S3IncrementalUploader:
    """
    Incremental S3 uploader for memory-efficient uploads of large datasets.
    
    Instead of accumulating all files and uploading at the end, this class
    allows uploading files immediately as they are generated, optionally
    deleting local files after successful upload to free disk space.
    
    Usage:
        uploader = S3IncrementalUploader('my-bucket', 'prefix/', 'aws-profile')
        
        # In your processing loop:
        for partition in partitions:
            process_partition(partition)
            write_parquet(partition, local_path)
            uploader.upload_file(local_path)  # or upload_and_delete()
        
        uploader.print_summary()
    """
    
    def __init__(self, bucket_name, s3_prefix="", aws_profile="", skip_profile=False, base_local_path=None):
        """
        Initialize the incremental uploader.
        
        Parameters
        ----------
        bucket_name : str
            S3 bucket name
        s3_prefix : str, optional
            S3 prefix/path (default: "")
        aws_profile : str, optional
            AWS profile name (default: "", uses default profile)
        skip_profile : bool, optional
            If True, use empty credentials (for testing)
        base_local_path : str or Path, optional
            Base local path for calculating relative S3 keys
        """
        self.bucket_name = bucket_name
        self.s3_prefix = s3_prefix
        self.aws_profile = aws_profile
        self.base_local_path = Path(base_local_path) if base_local_path else None
        
        # Initialize S3 client
        if skip_profile:
            session = boto3.Session(
                aws_access_key_id="",
                aws_secret_access_key="",
                region_name="us-east-2"
            )
        elif not skip_profile and aws_profile:
            session = boto3.Session(profile_name=aws_profile)
        else:
            session = boto3.Session()
        
        self.s3_client = session.client('s3')
        
        # Track upload statistics
        self.uploaded_count = 0
        self.failed_count = 0
        self.deleted_count = 0
        self.failed_files = []
        
        print(f"S3 Incremental Uploader initialized:")
        print(f"  Bucket: {bucket_name}")
        if s3_prefix:
            print(f"  Prefix: {s3_prefix}")
        if aws_profile:
            print(f"  Profile: {aws_profile}")
    
    def _calculate_s3_key(self, local_path):
        """Calculate S3 key from local path."""
        local_path = Path(local_path)
        
        if self.base_local_path:
            try:
                relative_path = local_path.relative_to(self.base_local_path)
            except ValueError:
                # Not relative to base path, use filename only
                relative_path = local_path.name
        else:
            relative_path = local_path.name
        
        s3_key = f"{self.s3_prefix}/{relative_path}".strip('/').replace('\\', '/')
        return s3_key
    
    def upload_file(self, local_path, custom_s3_key=None):
        """
        Upload a single file to S3.
        
        Parameters
        ----------
        local_path : str or Path
            Path to local file to upload
        custom_s3_key : str, optional
            Custom S3 key (overrides automatic key calculation)
        
        Returns
        -------
        bool
            True if upload succeeded, False otherwise
        """
        local_path = Path(local_path)
        
        if not local_path.exists():
            print(f"Warning: File does not exist: {local_path}")
            return False
        
        s3_key = custom_s3_key or self._calculate_s3_key(local_path)
        
        try:
            print(f"  Uploading: {local_path.name} -> s3://{self.bucket_name}/{s3_key}")
            self.s3_client.upload_file(str(local_path), self.bucket_name, s3_key)
            self.uploaded_count += 1
            return True
        except Exception as e:
            print(f"  Error uploading {local_path}: {e}")
            self.failed_count += 1
            self.failed_files.append((str(local_path), str(e)))
            return False
    
    def upload_and_delete(self, local_path, custom_s3_key=None):
        """
        Upload a file to S3 and delete the local copy after successful upload.
        
        This is useful for freeing disk space during large batch processing.
        
        Parameters
        ----------
        local_path : str or Path
            Path to local file to upload and delete
        custom_s3_key : str, optional
            Custom S3 key (overrides automatic key calculation)
        
        Returns
        -------
        bool
            True if upload and delete succeeded, False otherwise
        """
        local_path = Path(local_path)
        
        if self.upload_file(local_path, custom_s3_key):
            try:
                local_path.unlink()
                self.deleted_count += 1
                return True
            except Exception as e:
                print(f"  Warning: Could not delete local file {local_path}: {e}")
                return True  # Upload succeeded, just couldn't delete
        return False
    
    def upload_directory(self, local_dir, delete_after=False):
        """
        Upload all files in a directory to S3.
        
        Parameters
        ----------
        local_dir : str or Path
            Directory containing files to upload
        delete_after : bool
            If True, delete local files after successful upload
        
        Returns
        -------
        int
            Number of files successfully uploaded
        """
        local_dir = Path(local_dir)
        
        if not local_dir.exists():
            print(f"Warning: Directory does not exist: {local_dir}")
            return 0
        
        files = list(local_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        
        if not files:
            print(f"No files found in {local_dir}")
            return 0
        
        uploaded = 0
        for file_path in files:
            if delete_after:
                if self.upload_and_delete(file_path):
                    uploaded += 1
            else:
                if self.upload_file(file_path):
                    uploaded += 1
        
        # Clean up empty directories if we deleted files
        if delete_after:
            try:
                # Remove empty subdirectories
                for subdir in sorted(local_dir.rglob("*"), reverse=True):
                    if subdir.is_dir() and not any(subdir.iterdir()):
                        subdir.rmdir()
            except Exception:
                pass
        
        return uploaded
    
    def print_summary(self):
        """Print upload summary statistics."""
        print("\n" + "=" * 60)
        print("S3 UPLOAD SUMMARY")
        print("=" * 60)
        print(f"Successfully uploaded: {self.uploaded_count} files")
        if self.deleted_count > 0:
            print(f"Local files deleted: {self.deleted_count}")
        if self.failed_count > 0:
            print(f"Failed uploads: {self.failed_count}")
            for file_path, error in self.failed_files:
                print(f"  - {file_path}: {error}")


def create_s3_uploader(bucket_name, s3_prefix="", aws_profile="", skip_profile=False, base_local_path=None):
    """
    Factory function to create an S3IncrementalUploader.
    
    Parameters
    ----------
    bucket_name : str
        S3 bucket name
    s3_prefix : str, optional
        S3 prefix/path
    aws_profile : str, optional
        AWS profile name
    skip_profile : bool, optional
        If True, use empty credentials
    base_local_path : str or Path, optional
        Base local path for calculating relative S3 keys
    
    Returns
    -------
    S3IncrementalUploader
        Configured uploader instance
    """
    return S3IncrementalUploader(
        bucket_name=bucket_name,
        s3_prefix=s3_prefix,
        aws_profile=aws_profile,
        skip_profile=skip_profile,
        base_local_path=base_local_path
    )


def upload_to_s3(local_path, bucket_name, s3_prefix="", aws_profile="", skip_profile=False):
    """
    Upload a file or directory to S3 bucket.
    
    Parameters
    ----------
    local_path : str or Path
        Path to local file or directory to upload
    bucket_name : str
        S3 bucket name
    s3_prefix : str, optional
        S3 prefix/path (default: "")
    aws_profile : str, optional
        AWS profile name (default: "", uses default profile)
    
    Returns
    -------
    tuple
        (uploaded_count, total_count) - number of successful uploads and total files
    """
    
    print(f"\nUploading to S3 bucket: {bucket_name}")
    if s3_prefix:
        print(f"S3 prefix: {s3_prefix}")
    if aws_profile:
        print(f"AWS profile: {aws_profile}")
    
    # Initialize S3 client
    if skip_profile:
        session = boto3.Session(aws_access_key_id="",
                                aws_secret_access_key="",
                               region_name="us-east-2")
    if not skip_profile and aws_profile:
        session = boto3.Session(profile_name=aws_profile)
    
    s3_client = session.client('s3')
    
    local_path = Path(local_path)
    
    # Check if path exists
    if not local_path.exists():
        print(f"Error: Path does not exist: {local_path}")
        return 0, 0
    
    # Collect files to upload
    files_to_upload = []
    
    if local_path.is_file():
        # Single file
        files_to_upload.append(local_path)
        base_path = local_path.parent
    else:
        # Directory - get all files recursively
        files_to_upload = list(local_path.rglob("*"))
        files_to_upload = [f for f in files_to_upload if f.is_file()]
        base_path = local_path
    
    if not files_to_upload:
        print("No files found to upload")
        return 0, 0
    
    print(f"Found {len(files_to_upload)} file(s) to upload")
    
    uploaded_count = 0
    failed_files = []
    
    for file_path in files_to_upload:
        # Calculate S3 key (relative path from base)
        relative_path = file_path.relative_to(base_path)
        s3_key = f"{s3_prefix}/{relative_path}".strip('/').replace('\\', '/')
        
        try:
            print(f"Uploading: {file_path} -> s3://{bucket_name}/{s3_key}")
            s3_client.upload_file(str(file_path), bucket_name, s3_key)
            uploaded_count += 1
        except Exception as e:
            print(f"Error uploading {file_path}: {e}")
            failed_files.append((str(file_path), str(e)))
    
    # Summary
    print("\n" + "=" * 60)
    print("UPLOAD SUMMARY")
    print("=" * 60)
    print(f"Successfully uploaded: {uploaded_count}/{len(files_to_upload)} files")
    
    if failed_files:
        print(f"\nFailed uploads: {len(failed_files)}")
        for file_path, error in failed_files:
            print(f"  - {file_path}: {error}")
    
    return uploaded_count, len(files_to_upload)


def main():
    """Command-line interface for S3 upload."""
    
    if len(sys.argv) < 3:
        print("Usage: python s3_upload.py <local_path> <bucket_name> [s3_prefix] [aws_profile]")
        print("\nExamples:")
        print("  # Upload a single file")
        print("  python s3_upload.py data/pois.parquet my-bucket pois/")
        print("\n  # Upload a directory recursively")
        print("  python s3_upload.py data/parquet my-bucket simulation_data/")
        print("\n  # Use specific AWS profile")
        print("  python s3_upload.py data/logs my-bucket logs/ my-aws-profile")
        sys.exit(1)
    
    local_path = sys.argv[1]
    bucket_name = sys.argv[2]
    s3_prefix = sys.argv[3] if len(sys.argv) > 3 else ""
    aws_profile = sys.argv[4] if len(sys.argv) > 4 else ""
    
    try:
        uploaded, total = upload_to_s3(local_path, bucket_name, s3_prefix, aws_profile)
        
        if uploaded == total and total > 0:
            print("\n✓ All files uploaded successfully!")
            sys.exit(0)
        elif uploaded > 0:
            print(f"\n⚠ Partial success: {uploaded}/{total} files uploaded")
            sys.exit(1)
        else:
            print("\n✗ Upload failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
