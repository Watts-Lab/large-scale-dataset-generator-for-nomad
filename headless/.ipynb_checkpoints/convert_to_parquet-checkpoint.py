#!/usr/bin/env python3
"""
Convert TravelJournal.csv and trajectories.tsv to partitioned parquet files by date.
TravelJournal: user_id, x, y, start_time, end_time, venue_id, timestamp, duration
Trajectories: user_id, x, y, timestamp, step
Partitioned by date in folders like: date=2025-07-01/part-0.parquet
Uploads to S3 bucket after conversion.

Supports incremental S3 uploads - upload each partition immediately after writing
to avoid memory/disk issues with large datasets.
"""

import pandas as pd
import pyarrow as pa
import numpy.random as npr
import pyarrow.parquet as pq
import re
import os
import sys
import boto3
from datetime import datetime
from pathlib import Path
from shapely import wkt

def parse_point_geometry(geometry_str):
    if pd.isna(geometry_str) or geometry_str == '':
        return None, None
    
    try:
        # Parse WKT string to shapely geometry
        geom = wkt.loads(str(geometry_str))
        if geom.is_empty:
            return None, None
        # Extract x, y from point geometry
        return geom.x, geom.y
    except Exception:
        return None, None

def convert_travel_journal_to_parquet(csv_path, output_dir, s3_uploader=None, delete_after_upload=False):
    """
    Convert TravelJournal.csv to partitioned parquet files.
    
    Parameters
    ----------
    csv_path : str
        Path to TravelJournal.csv file
    output_dir : str
        Directory to write partitioned parquet files
    s3_uploader : S3IncrementalUploader, optional
        If provided, upload each partition to S3 immediately after writing
    delete_after_upload : bool
        If True and s3_uploader is provided, delete local files after upload
    
    Returns
    -------
    Path
        Path to the output directory
    """
    
    print(f"Reading TravelJournal.csv from: {csv_path}")
    if s3_uploader:
        print(f"  Incremental S3 upload enabled (delete_after_upload={delete_after_upload})")
    
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    print(f"Loaded {len(df)} records")
    
    # Parse geometry to extract x, y coordinates
    print("Parsing geometry coordinates...")
    coords = df['venueGeometry'].apply(parse_point_geometry)
    df['x'], df['y'] = zip(*coords)
    
    # Convert time columns to datetime
    df['checkInTime'] = pd.to_datetime(df['checkInTime'])
    df['checkOutTime'] = pd.to_datetime(df['checkOutTime'])
    
    # Extract date from checkInTime for partitioning
    df['date'] = df['checkInTime'].dt.date
    
    # Select and rename columns for output
    output_df = df[[
        'agentId', 'x', 'y', 'checkInTime', 'checkOutTime', 'travelEndLocationId', 'date'
    ]].copy()
    
    # Rename columns to match requirements
    output_df = output_df.rename(columns={
        'agentId': 'user_id',
        'checkInTime': 'start_time', 
        'checkOutTime': 'end_time',
        'travelEndLocationId': 'venue_id'
    })
    
    # Add timestamp (unix timestamp from start_time)
    output_df['timestamp'] = output_df['start_time'].astype('int64') // 10**9
    
    # Add duration (difference between end_time and start_time in seconds)
    output_df['duration'] = (output_df['end_time'] - output_df['start_time']).dt.total_seconds()
    
    # Remove rows with missing coordinates
    output_df = output_df.dropna(subset=['x', 'y'])
    
    print(f"Processing {len(output_df)} records with valid coordinates")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Group by date and write parquet files
    print("Writing partitioned parquet files...")
    
    for date, group in output_df.groupby('date'):
        date_str = date.strftime('%Y-%m-%d')
        partition_dir = output_path / f"date={date_str}"
        partition_dir.mkdir(exist_ok=True)
        
        # Remove date column before writing (it's used for partitioning)
        group_to_write = group.drop(columns=['date'])
        
        # Convert to PyArrow table
        table = pa.Table.from_pandas(group_to_write)
        
        # Write parquet file
        parquet_file = partition_dir / "part-0.parquet"
        pq.write_table(table, parquet_file)
        
        print(f"  Wrote {len(group)} records to {parquet_file}")
        
        # Upload to S3 if uploader provided
        if s3_uploader:
            if delete_after_upload:
                s3_uploader.upload_and_delete(parquet_file)
                # Try to remove empty partition directory
                try:
                    partition_dir.rmdir()
                except OSError:
                    pass
            else:
                s3_uploader.upload_file(parquet_file)
    
    print(f"Conversion complete! Parquet files written to: {output_dir}")
    
    # Print summary statistics
    print("\nSummary:")
    print(f"Total records processed: {len(output_df)}")
    print(f"Date range: {output_df['date'].min()} to {output_df['date'].max()}")
    print(f"Unique dates: {output_df['date'].nunique()}")
    print(f"Unique users: {output_df['user_id'].nunique()}")
    print(f"Unique venues: {output_df['venue_id'].nunique()}")
    
    return output_path

def convert_trajectories_to_parquet(tsv_path, output_dir, s3_uploader=None, delete_after_upload=False):
    """
    Convert trajectories.tsv to partitioned parquet files.
    
    Parameters
    ----------
    tsv_path : str
        Path to trajectories.tsv file
    output_dir : str
        Directory to write partitioned parquet files
    s3_uploader : S3IncrementalUploader, optional
        If provided, upload each partition to S3 immediately after writing
    delete_after_upload : bool
        If True and s3_uploader is provided, delete local files after upload
    
    Returns
    -------
    Path
        Path to the output directory
    """
    
    print(f"Reading trajectories.tsv from: {tsv_path}")
    if s3_uploader:
        print(f"  Incremental S3 upload enabled (delete_after_upload={delete_after_upload})")
    
    # Read the TSV file
    df = pd.read_csv(tsv_path, sep='\t', low_memory=False)
    
    print(f"Loaded {len(df)} records")
    
    # Parse geometry to extract x, y coordinates
    print("Parsing geometry coordinates...")
    coords = df['location'].apply(parse_point_geometry)
    df['x'], df['y'] = zip(*coords)
    
    # Convert time column to datetime
    df['simulationTime'] = pd.to_datetime(df['simulationTime'], format="%Y-%m-%dT%H:%M:%S.%f", errors='coerce')

    # Drop any rows where the timestamp didn’t parse
    df = df.dropna(subset=["simulationTime"])
    
    # Extract date from simulationTime for partitioning
    df['date'] = df['simulationTime'].dt.date
    
    # Select and rename columns for output
    output_df = df[[
        'agentId', 'x', 'y', 'simulationTime', 'step', 'date'
    ]].copy()
    
    # Rename columns to match requirements
    output_df = output_df.rename(columns={
        'agentId': 'user_id',
        'simulationTime': 'timestamp'
    })
    
    # Convert timestamp to unix timestamp
    output_df['timestamp'] = output_df['timestamp'].astype('int64') // 10**9
    
    # Remove rows with missing coordinates
    output_df = output_df.dropna(subset=['x', 'y'])
    
    print(f"Processing {len(output_df)} records with valid coordinates")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Group by date and write parquet files
    print("Writing partitioned parquet files...")
    
    for date, group in output_df.groupby('date'):
        date_str = date.strftime('%Y-%m-%d')
        partition_dir = output_path / f"date={date_str}"
        partition_dir.mkdir(exist_ok=True)
        
        # Remove date column before writing (it's used for partitioning)
        group_to_write = group.drop(columns=['date'])
        
        # Convert to PyArrow table
        table = pa.Table.from_pandas(group_to_write)
        
        # Write parquet file
        parquet_file = partition_dir / "part-0.parquet"
        pq.write_table(table, parquet_file)
        
        print(f"  Wrote {len(group)} records to {parquet_file}")
        
        # Upload to S3 if uploader provided
        if s3_uploader:
            if delete_after_upload:
                s3_uploader.upload_and_delete(parquet_file)
                # Try to remove empty partition directory
                try:
                    partition_dir.rmdir()
                except OSError:
                    pass
            else:
                s3_uploader.upload_file(parquet_file)
    
    print(f"Conversion complete! Parquet files written to: {output_dir}")
    
    # Print summary statistics
    print("\nSummary:")
    print(f"Total records processed: {len(output_df)}")
    print(f"Date range: {output_df['date'].min()} to {output_df['date'].max()}")
    print(f"Unique dates: {output_df['date'].nunique()}")
    print(f"Unique users: {output_df['user_id'].nunique()}")
    print(f"Total steps: {output_df['step'].max()}")
    
    return output_path


def main():
    """Main function."""
    if len(sys.argv) < 4:
        print("Usage: python3 convert_to_parquet.py <travel_journal_csv> <trajectories_tsv> <base_output_directory> [s3_bucket] [s3_prefix] [s3_profile]")
        print("Example: python3 convert_to_parquet.py data/logs/TravelJournal.csv data/logs/trajectories.tsv data/parquet")
        print("Example with S3: python3 convert_to_parquet.py data/logs/TravelJournal.csv data/logs/trajectories.tsv data/parquet my-bucket travel-data")
        sys.exit(1)
    
    travel_journal_csv = sys.argv[1]
    trajectories_tsv = sys.argv[2]
    base_output_dir = sys.argv[3]
    s3_bucket = sys.argv[4] if len(sys.argv) > 4 else None
    s3_prefix = sys.argv[5] if len(sys.argv) > 5 else ""
    s3_profile = sys.argv[6] if len(sys.argv) > 6 else ""
    
    # Check if input files exist
    if not os.path.exists(travel_journal_csv):
        print(f"Error: TravelJournal CSV file not found: {travel_journal_csv}")
        sys.exit(1)
    
    if not os.path.exists(trajectories_tsv):
        print(f"Error: Trajectories TSV file not found: {trajectories_tsv}")
        sys.exit(1)
    
    try:
        # Convert TravelJournal.csv to parquet
        print("=" * 60)
        print("CONVERTING TRAVEL JOURNAL")
        print("=" * 60)
        travel_journal_dir = convert_travel_journal_to_parquet(travel_journal_csv, f"{base_output_dir}/travel_journal")
        
        # Convert trajectories.tsv to parquet
        print("\n" + "=" * 60)
        print("CONVERTING TRAJECTORIES")
        print("=" * 60)
        trajectories_dir = convert_trajectories_to_parquet(trajectories_tsv, f"{base_output_dir}/trajectories")
        
        # Upload to S3 if bucket specified
        if s3_bucket:
            print("\n" + "=" * 60)
            print("UPLOADING TO S3")
            print("=" * 60)
            
            # Upload travel journal
            print("Uploading Travel Journal...")
            upload_to_s3(travel_journal_dir, s3_bucket, f"{s3_prefix}/travel_journal", s3_profile)
            
            # Upload trajectories
            print("\nUploading Trajectories...")
            upload_to_s3(trajectories_dir, s3_bucket, f"{s3_prefix}/trajectories", s3_profile)
        else:
            print("\nSkipping S3 upload (no bucket specified)")
            
    except Exception as e:
        print(f"Error during conversion: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
