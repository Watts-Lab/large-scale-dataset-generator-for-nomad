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
import numpy.random as npr
import argparse
import sys
from pathlib import Path
from datetime import datetime


def generate_ping_times(t0: int,
                        t_end: int,
                        *,
                        beta_start: float | None = None,
                        beta_durations: float | None = None,
                        beta_ping: float = 5,
                        seed: int | None = None,
                        return_bursts: bool = False,
                        tz=None):
    """Generate absolute ping timestamps (seconds) within [t0, t_end].

    If return_bursts is True, also returns a list of (start_time, end_time)
    for bursts that produced at least one ping. If tz is provided, start/end
    are timezone-aware pandas Timestamps; otherwise they are Unix seconds (int).
    """
    rng = npr.default_rng(seed)

    # convert minutes→seconds
    beta_ping_s = beta_ping * 60
    beta_start_s = beta_start * 60 if beta_start is not None else None
    beta_dur_s = beta_durations * 60 if beta_durations is not None else None

    if beta_start_s is None and beta_dur_s is None:
        burst_start_points = np.array([0.0])
        burst_end_points = np.array([t_end - t0], dtype=float)
    else:
        est_n = int(3 * (t_end - t0) / beta_start_s) + 10
        inter_arrival_times = rng.exponential(scale=beta_start_s, size=est_n)
        burst_start_points = np.cumsum(inter_arrival_times)
        burst_start_points = burst_start_points[burst_start_points < (t_end - t0)]
        burst_durations = rng.exponential(scale=beta_dur_s, size=burst_start_points.size)
        burst_end_points = burst_start_points + burst_durations
        if burst_end_points.size > 0:
            burst_end_points[:-1] = np.minimum(burst_end_points[:-1], burst_start_points[1:])
            burst_end_points[-1] = min(burst_end_points[-1], t_end - t0)

    ping_times_chunks: list[np.ndarray] = []
    bursts_out = [] if return_bursts else None
    for start, end in zip(burst_start_points, burst_end_points):
        dur = end - start
        if dur <= 0:
            continue
        est_pings = int(3 * dur / beta_ping_s) + 10
        ping_intervals = rng.exponential(scale=beta_ping_s, size=est_pings)
        times_rel = np.cumsum(ping_intervals)
        times_rel = times_rel[times_rel < dur]
        if times_rel.size:
            ping_times_chunks.append(t0 + start + times_rel)
            if return_bursts:
                if tz is not None:
                    sdt = pd.to_datetime(t0 + start, unit='s', utc=True).tz_convert(tz)
                    edt = pd.to_datetime(t0 + end, unit='s', utc=True).tz_convert(tz)
                else:
                    sdt = int(t0 + start)
                    edt = int(t0 + end)
                bursts_out.append([sdt, edt])

    if not ping_times_chunks:
        if return_bursts:
            return np.array([], dtype=int), []
        return np.array([], dtype=int)
    ping = np.concatenate(ping_times_chunks).astype(int)
    if return_bursts:
        return ping, bursts_out
    return ping

def thin_traj_by_times(traj: pd.DataFrame,
                       ping_times: np.ndarray,
                       *,
                       deduplicate: bool = True) -> pd.DataFrame:
    """Apply ping_times to a dense traj via searchsorted thinning."""
    if ping_times.size == 0:
        return pd.DataFrame(columns=traj.columns)

    traj_ts = traj['timestamp'].to_numpy()
    tz = traj['datetime'].dt.tz

    idx = np.searchsorted(traj_ts, ping_times, side='right') - 1
    valid = idx >= 0
    idx = idx[valid]
    ping_times = ping_times[valid]

    if deduplicate:
        _, keep = np.unique(idx, return_index=True)
        idx = idx[keep]
        ping_times = ping_times[keep]

    sampled_traj = traj.iloc[idx].copy()
    sampled_traj['timestamp'] = ping_times
    sampled_traj['datetime'] = (
        pd.to_datetime(ping_times, unit='s', utc=True)
          .tz_convert(tz)
    )
    return sampled_traj


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
        """
    )
    
    parser.add_argument('input_dir', help='Input directory containing parquet files')
    parser.add_argument('output_dir', help='Output directory for sparsified parquet files')
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
    except Exception as e:
        print(f"Error during sparsification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
