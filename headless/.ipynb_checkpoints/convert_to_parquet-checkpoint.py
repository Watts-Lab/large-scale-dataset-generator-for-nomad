#!/usr/bin/env python3
"""
Convert TravelJournal.csv and trajectories.tsv to partitioned parquet files by date.
TravelJournal: user_id, x, y, start_time, end_time, venue_id, timestamp, duration
Trajectories: user_id, x, y, timestamp, step
Partitioned by date in folders like: date=2025-07-01/part-0.parquet
Uploads to S3 bucket after conversion.
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import re
import os
import sys
import boto3
from datetime import datetime
from pathlib import Path

def parse_point_geometry(geometry_str):
    """Parse POINT (x y) string and return x, y coordinates."""
    if pd.isna(geometry_str) or geometry_str == '':
        return None, None
    
    # Extract coordinates from POINT (x y) format
    match = re.search(r'POINT\s*\(\s*([\d.-]+)\s+([\d.-]+)\s*\)', str(geometry_str))
    if match:
        x = float(match.group(1))
        y = float(match.group(2))
        return x, y
    else:
        return None, None

def convert_travel_journal_to_parquet(csv_path, output_dir):
    """Convert TravelJournal.csv to partitioned parquet files."""
    
    print(f"Reading TravelJournal.csv from: {csv_path}")
    
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    print(f"Loaded {len(df)} records")
    
    # Parse geometry to extract x, y coordinates
    print("Parsing geometry coordinates...")
    coords = df['venueGeometry'].apply(parse_point_geometry)
    df['x'] = [coord[0] for coord in coords]
    df['y'] = [coord[1] for coord in coords]
    
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
    
    print(f"Conversion complete! Parquet files written to: {output_dir}")
    
    # Print summary statistics
    print("\nSummary:")
    print(f"Total records processed: {len(output_df)}")
    print(f"Date range: {output_df['date'].min()} to {output_df['date'].max()}")
    print(f"Unique dates: {output_df['date'].nunique()}")
    print(f"Unique users: {output_df['user_id'].nunique()}")
    print(f"Unique venues: {output_df['venue_id'].nunique()}")
    
    return output_path

def convert_trajectories_to_parquet(tsv_path, output_dir):
    """Convert trajectories.tsv to partitioned parquet files."""
    
    print(f"Reading trajectories.tsv from: {tsv_path}")
    
    # Read the TSV file
    df = pd.read_csv(tsv_path, sep='\t', low_memory=False)
    
    print(f"Loaded {len(df)} records")
    
    # Parse geometry to extract x, y coordinates
    print("Parsing geometry coordinates...")
    coords = df['location'].apply(parse_point_geometry)
    df['x'] = [coord[0] for coord in coords]
    df['y'] = [coord[1] for coord in coords]
    
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
    
    print(f"Conversion complete! Parquet files written to: {output_dir}")
    
    # Print summary statistics
    print("\nSummary:")
    print(f"Total records processed: {len(output_df)}")
    print(f"Date range: {output_df['date'].min()} to {output_df['date'].max()}")
    print(f"Unique dates: {output_df['date'].nunique()}")
    print(f"Unique users: {output_df['user_id'].nunique()}")
    print(f"Total steps: {output_df['step'].max()}")
    
    return output_path

def upload_to_s3(local_dir, bucket_name, s3_prefix="", s3_profile=""):
    """Upload parquet files to S3 bucket."""
    
    print(f"\nUploading parquet files to S3 bucket: {bucket_name}")
    
    # Initialize S3 client
    session = boto3.Session(profile_name=s3_profile)
    s3_client = session.client('s3')
    
    # Get all parquet files recursively
    local_path = Path(local_dir)
    parquet_files = list(local_path.rglob("*.parquet"))
    
    if not parquet_files:
        print("No parquet files found to upload")
        return
    
    print(f"Found {len(parquet_files)} parquet files to upload")
    
    uploaded_count = 0
    for parquet_file in parquet_files:
        # Calculate S3 key (relative path from local_dir)
        relative_path = parquet_file.relative_to(local_path)
        s3_key = f"{s3_prefix}/{relative_path}".strip('/')
        
        try:
            print(f"Uploading: {parquet_file} -> s3://{bucket_name}/{s3_key}")
            s3_client.upload_file(str(parquet_file), bucket_name, s3_key)
            uploaded_count += 1
        except Exception as e:
            print(f"Error uploading {parquet_file}: {e}")
    
    print(f"Successfully uploaded {uploaded_count}/{len(parquet_files)} files to S3")

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
