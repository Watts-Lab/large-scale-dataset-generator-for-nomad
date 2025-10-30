#USAGE: sh mvn.sh [full]
full_install=$1
if [ "$full_install" = "full" ]; then
    echo installing local dependencies
    pip install \
        geopandas==1.1.1 \
        overpass==0.7
    conda install -y pyarrow
    sudo yum update -y
    sudo yum install -y maven
    mvn install:install-file -Dfile=src/main/resources/libs/jts-1.13.1.jar -DgroupId=com.vividsolutions -DartifactId=jts -Dversion=1.13.1 -Dpackaging=jar
    mvn install:install-file -Dfile=src/main/resources/libs/geomason-1.5.2.jar -DgroupId=sim.util.geo -DartifactId=geomason -Dversion=1.5.2 -Dpackaging=jar
    mvn install:install-file -Dfile=src/main/resources/libs/mason-19.jar -DgroupId=sim -DartifactId=mason -Dversion=19 -Dpackaging=jar
    mvn install:install-file -Dfile=src/main/resources/libs/mason-tools-1.0.jar -DgroupId=at.granul -DartifactId=mason-tools -Dversion=1.0 -Dpackaging=jar
else
    echo not installing local dependencies
fi

mvn clean install

mkdir -p jar
cp target/pol-0.2-jar-with-dependencies.jar jar/pol.jar
# rm -rf target
