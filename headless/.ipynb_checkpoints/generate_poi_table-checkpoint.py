#!/usr/bin/env python3
"""
Generate a Points of Interest (POI) table from simulation output.

Combines all BuildingUnit tables (Apartments, Workplaces, Restaurants, Pubs, Classrooms)
and filters to only those visited by agents according to TravelJournal.csv.

Output POI table contains:
- id: BuildingUnit ID (matches travelEndLocationId in TravelJournal)
- venue_type: Type of venue (apartment, workplace, restaurant, pub, classroom)
- x, y: Coordinates
- geometry: POINT geometry string
- buildingId: Parent building ID
- neighborhoodId: Neighborhood identifier
- attractiveness: Venue attractiveness score
- personCapacity: Maximum capacity

Usage:
  python generate_poi_table.py <data_dir> <output_file>

Example:
  python generate_poi_table.py data/logs data/parquet/pois.parquet
  python generate_poi_table.py data/logs data/pois.csv
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import re
import sys
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


def load_building_units(data_dir):
    """Load all BuildingUnit tables and combine them with venue type labels."""
    
    data_path = Path(data_dir)
    
    # Define the BuildingUnit files and their venue types
    unit_files = {
        'ApartmentTable.tsv': 'apartment',
        'WorkplaceTable.tsv': 'workplace',
        'RestaurantTable.tsv': 'restaurant',
        'PubTable.tsv': 'pub',
        'ClassroomTable.tsv': 'classroom'
    }
    
    all_units = []
    
    for filename, venue_type in unit_files.items():
        file_path = data_path / filename
        
        if not file_path.exists():
            print(f"Warning: {filename} not found, skipping...")
            continue
        
        print(f"Loading {filename}...")
        df = pd.read_csv(file_path, sep='\t')
        
        # Add venue type
        df['venue_type'] = venue_type
        
        # Select relevant columns (adjust based on actual column names in files)
        columns_to_keep = ['id', 'venue_type', 'location', 'buildingId', 
                          'neighborhoodId', 'attractiveness', 'personCapacity']
        
        # Only keep columns that exist
        available_cols = [col for col in columns_to_keep if col in df.columns]
        df = df[available_cols]
        
        all_units.append(df)
        print(f"  Loaded {len(df)} {venue_type}s")
    
    if not all_units:
        raise ValueError("No BuildingUnit files found!")
    
    # Combine all units
    combined_df = pd.concat(all_units, ignore_index=True)
    print(f"\nTotal BuildingUnits loaded: {len(combined_df)}")
    
    return combined_df


def get_visited_locations(data_dir):
    """Get unique location IDs visited by agents from TravelJournal."""
    
    data_path = Path(data_dir)
    travel_journal_path = data_path / 'TravelJournal.csv'
    
    if not travel_journal_path.exists():
        raise FileNotFoundError(f"TravelJournal.csv not found in {data_dir}")
    
    print("\nLoading TravelJournal.csv...")
    df = pd.read_csv(travel_journal_path)
    
    # Get unique visited location IDs
    visited_locations = df['travelEndLocationId'].unique()
    print(f"Found {len(visited_locations)} unique visited locations")
    
    return set(visited_locations)


def generate_poi_table(data_dir, output_file):
    """Generate POI table with only visited locations."""
    
    print("=" * 60)
    print("GENERATING POI TABLE")
    print("=" * 60)
    
    # Load all building units
    all_units = load_building_units(data_dir)
    
    # Get visited locations
    visited_locations = get_visited_locations(data_dir)
    
    # Filter to only visited locations
    print("\nFiltering to visited locations...")
    poi_df = all_units[all_units['id'].isin(visited_locations)].copy()
    
    print(f"POIs after filtering: {len(poi_df)}")
    
    if poi_df.empty:
        print("Warning: No matching POIs found!")
        return
    
    # Parse geometry to extract x, y coordinates
    print("\nParsing geometry coordinates...")
    coords = poi_df['location'].apply(parse_point_geometry)
    poi_df['x'] = [coord[0] for coord in coords]
    poi_df['y'] = [coord[1] for coord in coords]
    
    # Keep geometry as string for reference
    poi_df['geometry'] = poi_df['location']
    
    # Remove rows with missing coordinates
    poi_df = poi_df.dropna(subset=['x', 'y'])
    
    print(f"POIs with valid coordinates: {len(poi_df)}")
    
    # Reorder columns for output
    output_columns = ['id', 'venue_type', 'x', 'y', 'geometry']
    optional_columns = ['buildingId', 'neighborhoodId', 'attractiveness', 'personCapacity']
    
    for col in optional_columns:
        if col in poi_df.columns:
            output_columns.append(col)
    
    poi_df = poi_df[output_columns]
    
    # Remove location column if it exists (we kept geometry instead)
    if 'location' in poi_df.columns:
        poi_df = poi_df.drop(columns=['location'])
    
    # Write output
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_file.endswith('.parquet'):
        print(f"\nWriting POI table to parquet: {output_file}")
        table = pa.Table.from_pandas(poi_df)
        pq.write_table(table, output_path)
    elif output_file.endswith('.csv'):
        print(f"\nWriting POI table to CSV: {output_file}")
        poi_df.to_csv(output_path, index=False)
    else:
        raise ValueError("Output file must be .parquet or .csv")
    
    # Print summary
    print("\n" + "=" * 60)
    print("POI TABLE GENERATION COMPLETE")
    print("=" * 60)
    print(f"Total POIs: {len(poi_df)}")
    print(f"Output file: {output_file}")
    print("\nPOIs by venue type:")
    print(poi_df['venue_type'].value_counts().to_string())
    
    # Show sample
    print("\nSample POIs (first 5):")
    print(poi_df.head().to_string())


def main():
    if len(sys.argv) != 3:
        print("Usage: python generate_poi_table.py <data_dir> <output_file>")
        print("Example: python generate_poi_table.py data/logs data/parquet/pois.parquet")
        print("Example: python generate_poi_table.py data/logs data/pois.csv")
        sys.exit(1)
    
    data_dir = sys.argv[1]
    output_file = sys.argv[2]
    
    # Check if data directory exists
    if not Path(data_dir).exists():
        print(f"Error: Data directory not found: {data_dir}")
        sys.exit(1)
    
    try:
        generate_poi_table(data_dir, output_file)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
