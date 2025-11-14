#!/usr/bin/env python3
"""
Sparsify trajectory parquet files using thin_traj_by_times.

Reads partitioned parquet files created by convert_to_parquet.py and applies
trajectory sparsification using ping times generated with realistic burst/gap patterns
or uniform sampling.

Usage:
  python sparsify_parquet.py <input_parquet_dir> <output_parquet_dir> [options]

Options:
  --beta-start MINUTES      Mean time between bursts (default: 120 = 2 hours)
  --beta-durations MINUTES  Mean burst duration (default: 30 minutes)
  --beta-ping MINUTES       Mean time between pings within burst (default: 5 minutes)
  --uniform MINUTES         Use uniform sampling every N minutes (ignores burst params)
  --seed INT                Random seed for reproducibility (default: 42)
  --no-deduplicate          Don't remove duplicate trajectory indices

Example:
  # Realistic mobile phone pattern (bursts every ~2 hours, lasting ~30 min, pings every ~5 min)
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse
  
  # Uniform sampling every 15 minutes
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --uniform 15
  
  # Custom burst pattern
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --beta-start 60 --beta-durations 20 --beta-ping 3
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np
import argparse
import sys
import boto3
from pathlib import Path
from datetime import datetime

# Import thinning functions from traj_gen
from traj_gen import generate_ping_times, thin_traj_by_times


def sparsify_trajectories_parquet(
    input_dir,
    output_dir,
    beta_start=None,
    beta_durations=None,
    beta_ping=5,
    uniform_minutes=None,
    seed=42,
    deduplicate=True
):
    """
    Sparsify trajectory parquet files using thin_traj_by_times.
    
    Parameters
    ----------
    input_dir : str or Path
        Directory containing partitioned parquet files (date=YYYY-MM-DD/part-*.parquet)
    output_dir : str or Path
        Directory to write sparsified parquet files
    beta_start : float, optional
        Mean time between bursts in minutes (default: None, single continuous burst)
    beta_durations : float, optional
        Mean burst duration in minutes (default: None)
    beta_ping : float
        Mean time between pings within burst in minutes (default: 5)
    uniform_minutes : float, optional
        If set, use uniform sampling every N minutes instead of burst pattern
    seed : int
        Random seed for reproducibility
    deduplicate : bool
        Remove duplicate trajectory indices (default: True)
    """
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Find all parquet files
    parquet_files = sorted(input_path.rglob("*.parquet"))
    
    if not parquet_files:
        print(f"No parquet files found in {input_dir}")
        return
    
    print(f"Found {len(parquet_files)} parquet file(s) to sparsify")
    print(f"Sparsification parameters:")
    if uniform_minutes:
        print(f"  Mode: Uniform sampling every {uniform_minutes} minutes")
    else:
        print(f"  Mode: Burst pattern")
        print(f"    beta_start: {beta_start} minutes (time between bursts)")
        print(f"    beta_durations: {beta_durations} minutes (burst duration)")
        print(f"    beta_ping: {beta_ping} minutes (time between pings)")
    print(f"  seed: {seed}")
    print(f"  deduplicate: {deduplicate}")
    print()
    
    total_input_records = 0
    total_output_records = 0
    
    # Process each partition separately
    for parquet_file in parquet_files:
        print(f"Processing: {parquet_file.relative_to(input_path)}")
        
        # Read parquet file
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
        if df.empty:
            print(f"  Skipping empty file")
            continue
        
        total_input_records += len(df)
        
        # Convert timestamp back to datetime for traj_gen compatibility
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        
        # Process each user separately (thinning is per-user)
        sparse_dfs = []
        
        for user_id in df['user_id'].unique():
            user_traj = df[df['user_id'] == user_id].copy()
            user_traj = user_traj.sort_values('timestamp').reset_index(drop=True)
            
            if len(user_traj) == 0:
                continue
            
            # Get time window for this user
            t0 = int(user_traj['timestamp'].iloc[0])
            t_end = int(user_traj['timestamp'].iloc[-1])
            
            # Generate ping times
            if uniform_minutes:
                # Uniform sampling
                ping_times = np.arange(t0, t_end, uniform_minutes * 60, dtype=int)
            else:
                # Burst pattern using generate_ping_times
                ping_times = generate_ping_times(
                    t0, t_end,
                    beta_start=beta_start,
                    beta_durations=beta_durations,
                    beta_ping=beta_ping,
                    seed=seed
                )
            
            if len(ping_times) == 0:
                continue
            
            # Thin trajectory
            sparse_user_traj = thin_traj_by_times(user_traj, ping_times, deduplicate=deduplicate)
            
            if not sparse_user_traj.empty:
                sparse_dfs.append(sparse_user_traj)
        
        if not sparse_dfs:
            print(f"  No data after sparsification, skipping")
            continue
        
        # Combine all users
        sparse_df = pd.concat(sparse_dfs, ignore_index=True)
        
        # Remove datetime and date columns (datetime was temporary, date comes from partition path)
        cols_to_drop = [col for col in ['datetime', 'date'] if col in sparse_df.columns]
        if cols_to_drop:
            sparse_df = sparse_df.drop(columns=cols_to_drop)
        
        total_output_records += len(sparse_df)
        
        # Create output partition directory matching input structure
        relative_path = parquet_file.relative_to(input_path)
        output_partition_dir = output_path / relative_path.parent
        output_partition_dir.mkdir(parents=True, exist_ok=True)
        
        # Write sparsified parquet file
        output_file = output_partition_dir / parquet_file.name
        table_out = pa.Table.from_pandas(sparse_df)
        pq.write_table(table_out, output_file)
        
        reduction = (1 - len(sparse_df) / len(df)) * 100
        print(f"  Input: {len(df)} records, Output: {len(sparse_df)} records ({reduction:.1f}% reduction)")
        print(f"  Wrote: {output_file.relative_to(output_path)}")
    
    print()
    print("=" * 60)
    print("SPARSIFICATION COMPLETE")
    print("=" * 60)
    print(f"Total input records: {total_input_records}")
    print(f"Total output records: {total_output_records}")
    total_reduction = (1 - total_output_records / total_input_records) * 100 if total_input_records > 0 else 0
    print(f"Overall reduction: {total_reduction:.1f}%")
    print(f"Output written to: {output_path}")


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
    parser = argparse.ArgumentParser(
        description='Sparsify trajectory parquet files using thin_traj_by_times',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: bursts every ~2 hours, lasting ~30 min, pings every ~5 min
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse
  
  # Uniform sampling every 15 minutes
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --uniform 15
  
  # Custom burst pattern: bursts every hour, lasting 20 min, pings every 3 min
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --beta-start 60 --beta-durations 20 --beta-ping 3
  
  # With S3 upload
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse my-bucket trajectories_sparse
        """
    )
    
    parser.add_argument('input_dir', help='Input directory containing parquet files')
    parser.add_argument('output_dir', help='Output directory for sparsified parquet files')
    parser.add_argument('s3_bucket', nargs='?', default=None, help='S3 bucket name (optional)')
    parser.add_argument('s3_prefix', nargs='?', default='', help='S3 prefix/path (optional)')
    parser.add_argument('s3_profile', nargs='?', default='', help='AWS profile name (optional)')
    parser.add_argument('--beta-start', type=float, default=120,
                        help='Mean time between bursts in minutes (default: 120)')
    parser.add_argument('--beta-durations', type=float, default=30,
                        help='Mean burst duration in minutes (default: 30)')
    parser.add_argument('--beta-ping', type=float, default=5,
                        help='Mean time between pings within burst in minutes (default: 5)')
    parser.add_argument('--uniform', type=float, metavar='MINUTES',
                        help='Use uniform sampling every N minutes (ignores burst params)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for reproducibility (default: 42)')
    parser.add_argument('--no-deduplicate', action='store_true',
                        help="Don't remove duplicate trajectory indices")
    
    args = parser.parse_args()
    
    # Check if input directory exists
    if not Path(args.input_dir).exists():
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    try:
        sparsify_trajectories_parquet(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            beta_start=args.beta_start if not args.uniform else None,
            beta_durations=args.beta_durations if not args.uniform else None,
            beta_ping=args.beta_ping,
            uniform_minutes=args.uniform,
            seed=args.seed,
            deduplicate=not args.no_deduplicate
        )
        
        # Upload to S3 if bucket specified
        if args.s3_bucket:
            print("\n" + "=" * 60)
            print("UPLOADING TO S3")
            print("=" * 60)
            trajectories_sparse_dir = Path(args.output_dir)
            s3_prefix = f"{args.s3_prefix}/trajectories_sparse" if args.s3_prefix else "trajectories_sparse"
            upload_to_s3(trajectories_sparse_dir, args.s3_bucket, s3_prefix, args.s3_profile)
        else:
            print("\nSkipping S3 upload (no bucket specified)")
            
    except Exception as e:
        print(f"Error during sparsification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
