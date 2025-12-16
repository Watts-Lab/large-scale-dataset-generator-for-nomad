# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: conda_python3
#     language: python
#     name: conda_python3
# ---

# %% [markdown]
# # Virtual Philadelphia

# %% [markdown]
# ### basic imports

# %%
import subprocess
import sys
import shutil
import os
from datetime import datetime

# %% [markdown]
# ### install local dependencies and build pol.jar file

# %%
CURRENT_DIR = os.path.dirname(os.path.abspath('large-scale-dataset-generator-for-nomad'))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

process = subprocess.Popen(
    ["bash", "mvn.sh", "full"],
    cwd=PARENT_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

for line in process.stdout:
    print(line, end="")

# %% [markdown]
# ### install utility modules

# %%
import map_generation.utils.pqgis as pqgis
import utils.file as file
from s3_upload import upload_to_s3
from convert_to_parquet import convert_travel_journal_to_parquet, convert_trajectories_to_parquet
from sparsify_parquet import sparsify_trajectories_parquet
from generate_poi_table import generate_poi_table

# %% [markdown]
# ### generate run ID and create directory structure

# %%
RUN_DIR = "geolife_plus_phl"
LOGS_DIR = os.path.join(RUN_DIR, "logs")
PARQUET_DIR = os.path.join(RUN_DIR, "parquet")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(PARQUET_DIR, exist_ok=True)

# print("RUN_ID:", RUN_ID)
print("RUN_DIR:", RUN_DIR)
print("LOGS_DIR:", LOGS_DIR)
print("PARQUET_DIR:", PARQUET_DIR)

# %% [markdown]
# ### Set S3 config here (enter AWS profile name where it says s3_profile)

# %%
s3_bucket = "catalog-onspatial"
s3_traj_prefix = f"{RUN_DIR}/device-level/trajectories"
s3_sparse_prefix = f"{RUN_DIR}/device-level/trajectories_sparse"
s3_diaries_prefix = f"{RUN_DIR}/diaries"
s3_poi_prefix = f"{RUN_DIR}/poi_table"
s3_profile = "707813031043-PennResearchAssistant"

# %% [markdown]
# ### set bounding box and output folder for generated map

# %%
bounding_box = [-75.19747721789525, 39.931392279878246, -75.14652246706544, 39.96336810441389]
output_folder = '/run/user/1000/maps/philadelphia'

# %%
pqgis.generate_map(bounding_box, output_folder, new_map=True)

# %%
# # copy map to local directory
shutil.copytree('/run/user/1000/maps/philadelphia', 'maps/philadelphia', dirs_exist_ok=True)


# %% [markdown]
# ### edit modified.properties to set any relevant parameters before continuing

# %%
def merge_properties(base_path, override_path, output_path):
    merged = {}

    def load_file(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" not in line or line.startswith("#"):
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                merged[key] = f"{key}={value.strip()}"

    # Load files in order – second file overrides first
    load_file(base_path)
    load_file(override_path)

    # Write the merged output
    with open(output_path, "w") as f:
        for line in merged.values():
            f.write(line + "\n")


# Usage
MERGED_CONFIG = "./merged.properties"
merge_properties("../parameters.properties", "modified.properties", MERGED_CONFIG)

# %% [markdown]
# ### launch simulation

# %%
# SET LENGTH OF SIMULATION = simulation_time * time step (default = 5 min, multiply 288 by number of days)
simulation_time = "105120"

cmd = [
    "java",
    "-Dpol.gui=false",
    "-Djava.awt.headless=true",
    "-Dlog4j2.configurationFactory=pol.log.CustomConfigurationFactory",
    f"-Dlog.rootDirectory={RUN_DIR}",
    f"-Dsimulation.test=all",
    "-jar", "../jar/pol.jar",
    "-configuration", MERGED_CONFIG,
    "-until", simulation_time
]

result = subprocess.run(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

print(result.stdout)
print(result.stderr)

# %% [markdown]
# ### generate trajectories using integrate.py

# %%
file_prefix = "AgentStateTable"
appended_file = "trajectories.tsv"
print(f"Integrating log files from {LOGS_DIR} with prefix {file_prefix} into {appended_file}")
if file_prefix=='Checkin':
    file.integrate_log_files(f"/home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/{LOGS_DIR}", 
                             file_prefix, f"/home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/{LOGS_DIR}/trajectories.tsv", remove_original=True)
elif file_prefix=='AgentStateTable':
    file.integrate_log_files(f"/home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/{LOGS_DIR}", 
                             file_prefix, f"/home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/{LOGS_DIR}/trajectories.tsv", command='cut -f 1-4')

# %% [markdown]
# ### convert trajectories and stops to parquet, upload to S3 (set up AWS config beforehand)

# %%
travel_journal_csv = os.path.join(LOGS_DIR, "TravelJournal.csv")
trajectories_tsv = os.path.join(LOGS_DIR, "trajectories.tsv")
base_output_dir = PARQUET_DIR

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
        upload_to_s3(travel_journal_dir, s3_bucket, s3_diaries_prefix, s3_profile)
            
        # Upload trajectories
        print("\nUploading Trajectories...")
        upload_to_s3(trajectories_dir, s3_bucket, s3_traj_prefix, s3_profile)
    else:
        print("\nSkipping S3 upload (no bucket specified)")
            
except Exception as e:
    print(f"Error during conversion: {e}")

# %% [markdown]
# ### sparsify the trajectories using sparsify_parquet.py and upload to S3

# %%
# Sparsify trajectory parquet files using thin_traj_by_times.

# Reads partitioned parquet files created by convert_to_parquet.py and applies
# trajectory sparsification using ping times generated with realistic burst/gap patterns
# or uniform sampling.

# Usage:
#   python sparsify_parquet.py <input_parquet_dir> <output_parquet_dir> [options]

# Options:
#   --beta-start MINUTES      Mean time between bursts (default: 120 = 2 hours)
#   --beta-durations MINUTES  Mean burst duration (default: 30 minutes)
#   --beta-ping MINUTES       Mean time between pings within burst (default: 5 minutes)
#   --uniform MINUTES         Use uniform sampling every N minutes (ignores burst params)
#   --seed INT                Random seed for reproducibility (default: 42)
#   --no-deduplicate          Don't remove duplicate trajectory indices

# Example:
#   # Realistic mobile phone pattern (bursts every ~2 hours, lasting ~30 min, pings every ~5 min)
#   python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse
  
#   # Uniform sampling every 15 minutes
#   python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --uniform 15
  
#   # Custom burst pattern
#   python sparsify_parquet.py data/parquet/trajectories data/parquet/trajectories_sparse --beta-start 60 --beta-durations 20 --beta-ping 3

# %%
# set options
beta_start = 300
beta_durations = 55
beta_ping = 7
seed = 0
uniform = None
deduplicate = True

try:
    sparsify_trajectories_parquet(
        input_dir=f"{PARQUET_DIR}/trajectories",
        output_dir=f"{PARQUET_DIR}/trajectories_sparse",
        beta_start=beta_start,
        beta_durations=beta_durations,
        beta_ping=beta_ping,
        uniform_minutes=uniform,
        seed=seed,
        deduplicate=deduplicate
    )
        
    # Upload to S3 if bucket specified
    try:
        upload_to_s3(f"{PARQUET_DIR}/trajectories_sparse", s3_bucket, s3_sparse_prefix, s3_profile)
    except Exception as e:
        print("S3 upload failed")
            
except Exception as e:
    print(f"Error during sparsification: {e}")
    import traceback
    traceback.print_exc()

# %% [markdown]
# ### generate POI table (visited by agents) and upload to S3

# %%
try:
    generate_poi_table(LOGS_DIR, f"{RUN_DIR}/poi_table_visited.parquet")
    try:
        upload_to_s3(f"{RUN_DIR}/poi_table_visited.parquet", s3_bucket, s3_poi_prefix, s3_profile)
    except Exception as e:
        print("S3 upload failed")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# %%
