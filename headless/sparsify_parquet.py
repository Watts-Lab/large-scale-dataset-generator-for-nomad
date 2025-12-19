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
  --incremental             Process partition-by-partition (memory efficient for large data)
  --s3-upload-incremental   Upload each partition to S3 immediately after processing
  --delete-after-upload     Delete local files after successful S3 upload (saves disk space)

Example:
  # Realistic mobile phone pattern (bursts every ~2 hours, lasting ~30 min, pings every ~5 min)
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse
  
  # Uniform sampling every 15 minutes
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --uniform 15
  
  # Custom burst pattern
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --beta-start 60 --beta-durations 20 --beta-ping 3
  
  # Memory-efficient incremental processing with immediate S3 upload
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --incremental --s3-upload-incremental my-bucket prefix --delete-after-upload
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np
import numpy.random as npr
import argparse
import sys
import boto3
from pathlib import Path
from datetime import datetime

# Import thinning functions from traj_gen
from traj_gen import generate_ping_times, thin_traj_by_times, _sample_horizontal_noise


def sparsify_trajectories_parquet(
    input_dir,
    output_dir,
    beta_start=None,
    beta_durations=None,
    beta_ping=5,
    uniform_minutes=None,
    output_bursts=False,
    seed=42,
    deduplicate=True,
    ha=3/4,
    s3_uploader=None,
    delete_after_upload=False,
    delete_input_after_processing=False
):
    """
    Sparsify trajectory parquet files using thin_traj_by_times.
    
    Loads all data at once and processes each user's full trajectory, ensuring
    consistent ping time generation across all days. Optionally uploads each
    date partition to S3 incrementally after writing.
    
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
    s3_uploader : S3IncrementalUploader, optional
        If provided, upload each date partition to S3 after writing
    delete_after_upload : bool
        If True and s3_uploader is provided, delete local sparse files after upload
    delete_input_after_processing : bool
        If True, delete the input trajectory directory after all processing is complete
    
    Returns
    -------
    tuple
        (total_input_records, total_output_records)
    """
    import shutil
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Sparsification parameters:")
    if uniform_minutes is not None:
        print(f"  Mode: Uniform sampling every {uniform_minutes} minutes")
    else:
        print(f"  Mode: Burst pattern")
        print(f"    beta_start: {beta_start} minutes (time between bursts)")
        print(f"    beta_durations: {beta_durations} minutes (burst duration)")
        print(f"    beta_ping: {beta_ping} minutes (time between pings)")
    print(f"  seed: {seed} (base seed, per-user seeds will be sequential)")
    print(f"  deduplicate: {deduplicate}")
    if s3_uploader:
        print(f"  S3 upload: enabled (delete_after_upload={delete_after_upload})")
    if delete_input_after_processing:
        print(f"  Delete input after processing: enabled")
    print()
    
    # Read all parquet files at once
    print(f"Reading all parquet files from {input_path}...")
    df = pd.read_parquet(input_path)
    
    if df.empty:
        print(f"No data found in {input_dir}")
        return
    
    total_input_records = len(df)
    print(f"Loaded {total_input_records} records from all partitions")
    
    # Convert timestamp back to datetime for traj_gen compatibility
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
    
    # Get all unique users and assign sequential seeds
    all_user_ids = sorted(df['user_id'].unique())
    print(f"Processing {len(all_user_ids)} unique users...")
    
    # Process each user separately (thinning is per-user)
    sparse_dfs = []
    
    for i, user_id in enumerate(all_user_ids):
        
        user_traj = df[df['user_id'] == user_id].copy()
        user_traj = user_traj.sort_values('timestamp').reset_index(drop=True)
        
        if len(user_traj) == 0:
            continue
        
        # Get time window for this user
        t0 = int(user_traj['timestamp'].iloc[0])
        t_end = int(user_traj['timestamp'].iloc[-1])
        
        # Use sequential seed for each user
        user_seed = i
        
        # Generate ping times
        tz = user_traj['datetime'].dt.tz
        
        # Handle uniform sampling mode
        if uniform_minutes is not None:
            # Uniform sampling: create ping times at regular intervals
            interval_seconds = uniform_minutes * 60
            ping_times = np.arange(t0, t_end, interval_seconds, dtype=int)
        elif output_bursts:
            ping_times = generate_ping_times(
                t0, t_end,
                beta_start=beta_start,
                beta_durations=beta_durations,
                beta_ping=beta_ping,
                seed=user_seed,
                return_bursts=True,
                tz=tz
            )
        else:
            # Burst pattern using generate_ping_times
            ping_times = generate_ping_times(
                t0, t_end,
                beta_start=beta_start,
                beta_durations=beta_durations,
                beta_ping=beta_ping,
                seed=user_seed
            )
        
        if len(ping_times) == 0:
            continue
        
        # Thin trajectory
        sparse_user_traj = thin_traj_by_times(user_traj, ping_times, deduplicate=deduplicate)

        # add horizontal noise using per-user seed
        rng = npr.default_rng(user_seed)
        n = len(sparse_user_traj)
        ha_realized, noise = _sample_horizontal_noise(n, ha=ha, rng=rng)
        sparse_user_traj['ha'] = ha_realized
        sparse_user_traj[['x', 'y']] += noise
        
        if not sparse_user_traj.empty:
            sparse_dfs.append(sparse_user_traj)
    
    print(f"  Processed {len(all_user_ids)}/{len(all_user_ids)} users.")
    
    if not sparse_dfs:
        print(f"No data after sparsification")
        return
    
    # Combine all users
    print("Combining all sparsified trajectories...")
    sparse_df = pd.concat(sparse_dfs, ignore_index=True)
    
    # Remove datetime column (temporary column)
    if 'datetime' in sparse_df.columns:
        sparse_df = sparse_df.drop(columns=['datetime'])
    
    total_output_records = len(sparse_df)
    
    # Write output as partitioned parquet (by date if available, or as single file)
    print("Writing output parquet files...")
    if 'date' in sparse_df.columns:
        # Write partitioned by date - do it manually so we can upload each partition
        unique_dates = sparse_df['date'].unique()
        for date_val in sorted(unique_dates):
            date_str = str(date_val)
            partition_dir = output_path / f"date={date_str}"
            partition_dir.mkdir(exist_ok=True)
            
            # Get data for this date and drop the date column
            date_df = sparse_df[sparse_df['date'] == date_val].drop(columns=['date'])
            
            # Write parquet file
            output_file = partition_dir / "part-0.parquet"
            date_df.to_parquet(output_file, engine='pyarrow', index=False)
            print(f"  Wrote {len(date_df)} records to {output_file}")
            
            # Upload to S3 if uploader provided
            if s3_uploader:
                if delete_after_upload:
                    s3_uploader.upload_and_delete(output_file)
                    # Try to remove empty partition directory
                    try:
                        partition_dir.rmdir()
                    except OSError:
                        pass
                else:
                    s3_uploader.upload_file(output_file)
    else:
        # Write as single parquet file
        output_file = output_path / "trajectories_sparse.parquet"
        sparse_df.to_parquet(output_file, engine='pyarrow', index=False)
        print(f"  Wrote {output_file}")
        
        # Upload to S3 if uploader provided
        if s3_uploader:
            if delete_after_upload:
                s3_uploader.upload_and_delete(output_file)
            else:
                s3_uploader.upload_file(output_file)
    
    print()
    print("=" * 60)
    print("SPARSIFICATION COMPLETE")
    print("=" * 60)
    print(f"Total input records: {total_input_records}")
    print(f"Total output records: {total_output_records}")
    total_reduction = (1 - total_output_records / total_input_records) * 100 if total_input_records > 0 else 0
    print(f"Overall reduction: {total_reduction:.1f}%")
    print(f"Output written to: {output_path}")
    
    if s3_uploader:
        s3_uploader.print_summary()
    
    # Delete input directory if requested
    if delete_input_after_processing:
        print()
        print("Cleaning up input directory...")
        try:
            shutil.rmtree(input_path)
            print(f"  Deleted: {input_path}")
        except Exception as e:
            print(f"  Warning: Could not delete input directory {input_path}: {e}")
    
    # Try to clean up output directory if empty (all files uploaded and deleted)
    if delete_after_upload and s3_uploader:
        try:
            remaining_files = list(output_path.rglob("*"))
            remaining_files = [f for f in remaining_files if f.is_file()]
            if not remaining_files:
                shutil.rmtree(output_path)
                print(f"  Deleted empty output directory: {output_path}")
        except Exception:
            pass
    
    return total_input_records, total_output_records


def sparsify_trajectories_parquet_incremental(
    input_dir,
    output_dir,
    beta_start=None,
    beta_durations=None,
    beta_ping=5,
    uniform_minutes=None,
    output_bursts=False,
    seed=42,
    deduplicate=True,
    ha=3/4,
    s3_uploader=None,
    delete_after_upload=False,
    delete_input_after_processing=False
):
    """
    Sparsify trajectory parquet files incrementally, partition by partition.
    
    This is a memory-efficient version that processes one date partition at a time,
    optionally uploading to S3 and deleting local files after each partition.
    
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
    s3_uploader : S3IncrementalUploader, optional
        If provided, upload each partition to S3 after processing
    delete_after_upload : bool
        If True and s3_uploader is provided, delete local sparse files after upload
    delete_input_after_processing : bool
        If True, delete the input trajectory directory after all processing is complete.
        Useful when you want to clean up both input and output files after S3 upload.
    
    Returns
    -------
    tuple
        (total_input_records, total_output_records)
    """
    from s3_upload import S3IncrementalUploader
    import shutil
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"INCREMENTAL SPARSIFICATION MODE")
    print(f"Sparsification parameters:")
    if uniform_minutes is not None:
        print(f"  Mode: Uniform sampling every {uniform_minutes} minutes")
    else:
        print(f"  Mode: Burst pattern")
        print(f"    beta_start: {beta_start} minutes (time between bursts)")
        print(f"    beta_durations: {beta_durations} minutes (burst duration)")
        print(f"    beta_ping: {beta_ping} minutes (time between pings)")
    print(f"  seed: {seed} (base seed, per-user seeds will be sequential)")
    print(f"  deduplicate: {deduplicate}")
    if s3_uploader:
        print(f"  S3 upload: enabled (delete_after_upload={delete_after_upload})")
    if delete_input_after_processing:
        print(f"  Delete input after processing: enabled")
    print()
    
    # Find all date partitions
    partition_dirs = sorted([d for d in input_path.iterdir() if d.is_dir() and d.name.startswith('date=')])
    
    if not partition_dirs:
        print(f"No date partitions found in {input_dir}")
        return 0, 0
    
    print(f"Found {len(partition_dirs)} date partitions to process")
    
    # Build a global user_id -> seed mapping by scanning all partitions first
    print("Scanning all partitions to build user ID mapping...")
    all_user_ids = set()
    for partition_dir in partition_dirs:
        try:
            df_scan = pd.read_parquet(partition_dir)
            all_user_ids.update(df_scan['user_id'].unique())
        except Exception as e:
            print(f"  Warning: Could not scan {partition_dir}: {e}")
    
    all_user_ids = sorted(all_user_ids)
    user_id_to_seed = {uid: i for i, uid in enumerate(all_user_ids)}
    print(f"Found {len(all_user_ids)} unique users across all partitions")
    print()
    
    total_input_records = 0
    total_output_records = 0
    
    for partition_idx, partition_dir in enumerate(partition_dirs):
        date_str = partition_dir.name.replace('date=', '')
        print(f"Processing partition {partition_idx + 1}/{len(partition_dirs)}: {date_str}")
        
        try:
            # Read only this partition
            df = pd.read_parquet(partition_dir)
            
            if df.empty:
                print(f"  No data in partition {date_str}")
                continue
            
            partition_input_records = len(df)
            total_input_records += partition_input_records
            print(f"  Loaded {partition_input_records} records")
            
            # Convert timestamp back to datetime for traj_gen compatibility
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            
            # Get unique users in this partition
            partition_user_ids = sorted(df['user_id'].unique())
            
            # Process each user
            sparse_dfs = []
            
            for user_id in partition_user_ids:
                user_traj = df[df['user_id'] == user_id].copy()
                user_traj = user_traj.sort_values('timestamp').reset_index(drop=True)
                
                if len(user_traj) == 0:
                    continue
                
                # Get time window for this user
                t0 = int(user_traj['timestamp'].iloc[0])
                t_end = int(user_traj['timestamp'].iloc[-1])
                
                # Use consistent seed based on global user_id mapping
                user_seed = user_id_to_seed[user_id]
                
                # Generate ping times
                tz = user_traj['datetime'].dt.tz
                
                if uniform_minutes is not None:
                    interval_seconds = uniform_minutes * 60
                    ping_times = np.arange(t0, t_end, interval_seconds, dtype=int)
                elif output_bursts:
                    ping_times = generate_ping_times(
                        t0, t_end,
                        beta_start=beta_start,
                        beta_durations=beta_durations,
                        beta_ping=beta_ping,
                        seed=user_seed,
                        return_bursts=True,
                        tz=tz
                    )
                else:
                    ping_times = generate_ping_times(
                        t0, t_end,
                        beta_start=beta_start,
                        beta_durations=beta_durations,
                        beta_ping=beta_ping,
                        seed=user_seed
                    )
                
                if len(ping_times) == 0:
                    continue
                
                # Thin trajectory
                sparse_user_traj = thin_traj_by_times(user_traj, ping_times, deduplicate=deduplicate)
                
                # Add horizontal noise using per-user seed
                rng = npr.default_rng(user_seed)
                n = len(sparse_user_traj)
                ha_realized, noise = _sample_horizontal_noise(n, ha=ha, rng=rng)
                sparse_user_traj['ha'] = ha_realized
                sparse_user_traj[['x', 'y']] += noise
                
                if not sparse_user_traj.empty:
                    sparse_dfs.append(sparse_user_traj)
            
            if not sparse_dfs:
                print(f"  No data after sparsification for {date_str}")
                continue
            
            # Combine users for this partition
            sparse_df = pd.concat(sparse_dfs, ignore_index=True)
            
            # Remove datetime column
            if 'datetime' in sparse_df.columns:
                sparse_df = sparse_df.drop(columns=['datetime'])
            
            partition_output_records = len(sparse_df)
            total_output_records += partition_output_records
            
            partition_reduction = (1 - partition_output_records / partition_input_records) * 100 if partition_input_records > 0 else 0
            print(f"  Output: {partition_output_records} records ({partition_reduction:.1f}% reduction)")
            
            # Write partition output
            partition_output_dir = output_path / f"date={date_str}"
            partition_output_dir.mkdir(exist_ok=True)
            
            output_file = partition_output_dir / "part-0.parquet"
            sparse_df.to_parquet(output_file, engine='pyarrow', index=False)
            print(f"  Wrote: {output_file}")
            
            # Upload to S3 if uploader provided
            if s3_uploader:
                if delete_after_upload:
                    s3_uploader.upload_and_delete(output_file)
                    # Try to remove empty partition directory
                    try:
                        partition_output_dir.rmdir()
                    except OSError:
                        pass
                else:
                    s3_uploader.upload_file(output_file)
            
            # Clear memory
            del df, sparse_df, sparse_dfs
            
        except Exception as e:
            print(f"  Error processing partition {date_str}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print()
    print("=" * 60)
    print("INCREMENTAL SPARSIFICATION COMPLETE")
    print("=" * 60)
    print(f"Total input records: {total_input_records}")
    print(f"Total output records: {total_output_records}")
    total_reduction = (1 - total_output_records / total_input_records) * 100 if total_input_records > 0 else 0
    print(f"Overall reduction: {total_reduction:.1f}%")
    print(f"Output written to: {output_path}")
    
    if s3_uploader:
        s3_uploader.print_summary()
    
    # Delete input directory if requested
    if delete_input_after_processing:
        print()
        print("Cleaning up input directory...")
        try:
            shutil.rmtree(input_path)
            print(f"  Deleted: {input_path}")
        except Exception as e:
            print(f"  Warning: Could not delete input directory {input_path}: {e}")
    
    # Try to clean up output directory if empty (all files uploaded and deleted)
    if delete_after_upload and s3_uploader:
        try:
            # Check if output directory is empty or only has empty subdirs
            remaining_files = list(output_path.rglob("*"))
            remaining_files = [f for f in remaining_files if f.is_file()]
            if not remaining_files:
                shutil.rmtree(output_path)
                print(f"  Deleted empty output directory: {output_path}")
        except Exception:
            pass
    
    return total_input_records, total_output_records


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
  
  # With S3 upload (batch mode - upload after all processing)
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse my-bucket trajectories_sparse
  
  # Memory-efficient incremental mode with immediate S3 upload (recommended for large datasets)
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse \\
      --incremental --s3-bucket my-bucket --s3-prefix trajectories_sparse --s3-profile my-profile
  
  # Incremental mode with S3 upload AND local file deletion (saves disk space)
  python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse \\
      --incremental --s3-bucket my-bucket --s3-prefix trajectories_sparse --delete-after-upload
        """
    )
    
    parser.add_argument('input_dir', help='Input directory containing parquet files')
    parser.add_argument('output_dir', help='Output directory for sparsified parquet files')
    parser.add_argument('s3_bucket', nargs='?', default=None, help='S3 bucket name (optional, for batch upload after processing)')
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
    
    # Incremental processing options
    parser.add_argument('--incremental', action='store_true',
                        help='Process partition-by-partition (memory efficient for large datasets)')
    parser.add_argument('--s3-bucket', dest='s3_bucket_incremental', default=None,
                        help='S3 bucket for incremental upload (use with --incremental)')
    parser.add_argument('--s3-prefix', dest='s3_prefix_incremental', default='',
                        help='S3 prefix for incremental upload')
    parser.add_argument('--s3-profile', dest='s3_profile_incremental', default='',
                        help='AWS profile for incremental upload')
    parser.add_argument('--delete-after-upload', action='store_true',
                        help='Delete local files after successful S3 upload (saves disk space)')
    
    args = parser.parse_args()
    
    # Check if input directory exists
    if not Path(args.input_dir).exists():
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    try:
        if args.incremental:
            # Incremental mode - process partition by partition
            s3_uploader = None
            if args.s3_bucket_incremental:
                from s3_upload import create_s3_uploader
                s3_uploader = create_s3_uploader(
                    bucket_name=args.s3_bucket_incremental,
                    s3_prefix=args.s3_prefix_incremental,
                    aws_profile=args.s3_profile_incremental,
                    base_local_path=Path(args.output_dir)
                )
            
            sparsify_trajectories_parquet_incremental(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                beta_start=args.beta_start if not args.uniform else None,
                beta_durations=args.beta_durations if not args.uniform else None,
                beta_ping=args.beta_ping,
                uniform_minutes=args.uniform,
                seed=args.seed,
                deduplicate=not args.no_deduplicate,
                s3_uploader=s3_uploader,
                delete_after_upload=args.delete_after_upload
            )
        else:
            # Original batch mode
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
            
            # Upload to S3 if bucket specified (batch upload after all processing)
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
