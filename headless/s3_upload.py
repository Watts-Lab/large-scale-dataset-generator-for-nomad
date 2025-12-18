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
  from s3_upload import upload_to_s3
  upload_to_s3('data/parquet', 'my-bucket', 's3_prefix/', 'profile-name')
"""

import sys
import boto3
from pathlib import Path


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
