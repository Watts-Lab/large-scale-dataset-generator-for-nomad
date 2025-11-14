MERGED_CONFIG="./merged.properties"
# Merge parameters.properties and modified.properties, with modified.properties taking precedence
cat ../parameters.properties modified.properties | awk -F'=' '{key=$1; gsub(/^[ \t]+|[ \t]+$/, "", key); if (key != "") {a[key]=$0}} END {for (i in a) print a[i]}' > "$MERGED_CONFIG"

RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="data/run_${RUN_ID}"
LOGS_DIR="${RUN_DIR}/logs"
PARQUET_DIR="${RUN_DIR}/parquet"
mkdir -p "$LOGS_DIR" "$PARQUET_DIR"

java -Dpol.gui=false -Djava.awt.headless=true -Dlog4j2.configurationFactory=pol.log.CustomConfigurationFactory -Dlog.rootDirectory="$RUN_DIR" -Dsimulation.test=all -jar ../jar/pol.jar -configuration "$MERGED_CONFIG" -until 288

python3 ../src/main/python/code/data_generation/integrate.py /home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/$LOGS_DIR AgentStateTable /home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/$LOGS_DIR/trajectories.tsv

python3 convert_to_parquet.py $LOGS_DIR/TravelJournal.csv $LOGS_DIR/trajectories.tsv $PARQUET_DIR dedicated-raghav temp/geolife-X/device-level/$RUN_DIR 707813031043-PennResearchAssistant

python3 sparsify_parquet.py $PARQUET_DIR/trajectories $PARQUET_DIR/trajectories_sparse