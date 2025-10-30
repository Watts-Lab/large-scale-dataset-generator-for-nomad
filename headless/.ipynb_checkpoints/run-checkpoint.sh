MERGED_CONFIG="./merged.properties"
# Merge parameters.properties and modified.properties, with modified.properties taking precedence
cat ../parameters.properties modified.properties | awk -F'=' '{key=$1; gsub(/^[ \t]+|[ \t]+$/, "", key); if (key != "") {a[key]=$0}} END {for (i in a) print a[i]}' > "$MERGED_CONFIG"
java -Dpol.gui=false -Djava.awt.headless=true -Dlog4j2.configurationFactory=pol.log.CustomConfigurationFactory -Dlog.rootDirectory=data -Dsimulation.test=all -jar ../jar/pol.jar -configuration "$MERGED_CONFIG" -until 2880
python3 ../src/main/python/code/data_generation/integrate.py /home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/data/logs AgentStateTable /home/ec2-user/SageMaker/large-scale-dataset-generator-for-nomad/headless/data/logs/trajectories.tsv
python3 convert_to_parquet.py data/logs/TravelJournal.csv data/logs/trajectories.tsv data/parquet dedicated-raghav temp/geolife-X/device-level "707813031043-PennResearchAssistant"