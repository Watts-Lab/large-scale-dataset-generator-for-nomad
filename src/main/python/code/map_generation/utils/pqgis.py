import os

import geopandas as gpd
import utils.file  as file
import utils.geojson as geojson
import utils.pqgis as pqgis

def get_crs(gdf=None, which='default'):
    crs = 'epsg:4326'
    if which == 'default' and gdf is None:
        crs = 'EPSG:26916'
    elif gdf is not None:
        print("Calculating CRS based on geometry centroid")
        centroid = gdf.geometry.unary_union.centroid
        lon, lat = centroid.x, centroid.y
        zone = int((lon + 180) // 6) + 1
        is_northern = lat >= 0
        epsg_code = 32600 + zone if is_northern else 32700 + zone
        crs= f"EPSG:{epsg_code}"
    print(f"crs is set to {crs}")
    return crs

def get_buildings_shapeFile(buildings_geojson):
    print('Getting buildings shapefile')
    buildings = gpd.read_file(buildings_geojson)
    print(buildings.head())
    print(buildings.columns)
    buildings = buildings[['building', 'geometry']]
    crs=get_crs(buildings)
    buildings = buildings.to_crs(crs)
    buildings['id'] = range(1, len(buildings) + 1)
    buildings['function'] = buildings['building'].apply(lambda x: 1 if x in ['yes', 'house', 'apartments', 'residential', 'dormitory'] else 2)
    buildings['neighbor'] = 0
    buildings['degree'] = 1.0
    buildings = buildings.drop(columns=['building'])
    return buildings, crs

def get_walkways_shapeFile(walkways_geojson, crs):
    print('Getting walkways shapefile')
    walkways = gpd.read_file(walkways_geojson)
    walkways = walkways.to_crs(crs)
    walkways = walkways[['geometry']]  
    walkways['id'] = range(1, len(walkways) + 1)
    return walkways

def get_buildingUnits_shapeFile(buildings_shapeFile, crs):
    print('Getting building units shapefile')
    building_units = buildings_shapeFile.copy()
    building_units = building_units.to_crs(crs)
    building_units['geometry'] = building_units['geometry'].centroid
    building_units.rename(columns={'id': 'building'}, inplace=True)
    building_units = building_units[['building', 'geometry']]
    return building_units

def generate_map(bounding_box,output_folder, new_map=True):
    #CHANGE
    output_folder = os.path.abspath(output_folder)

    buildings_geojson_path= output_folder + '/buildings.geojson'
    walkways_geojson_path= output_folder + '/walkways.geojson'
    
    if not file.exists(buildings_geojson_path) or new_map:
        print('Getting buildings geojson from overpass')
        buildings_geojson = geojson.get_buildings_geojson(bounding_box)
        file.save_geojson(buildings_geojson, buildings_geojson_path)

    if not file.exists(walkways_geojson_path) or new_map:
        print('Getting walkways geojson from overpass')
        walkways_geojson = geojson.get_walkways_geojson(bounding_box)
        file.save_geojson(walkways_geojson, walkways_geojson_path)
    
    print('Generating map shapefiles')
    buildings_gdf, crs = pqgis.get_buildings_shapeFile(buildings_geojson_path)
    walkways_shapeFile = pqgis.get_walkways_shapeFile(walkways_geojson_path,crs)
    buildingUnits_shapeFile = pqgis.get_buildingUnits_shapeFile(buildings_gdf,crs)

    print(f'Saving shapefiles to {output_folder}')
    file.save_shapeFile(buildings_gdf, output_folder + '/map/buildings.shp')
    file.save_shapeFile(walkways_shapeFile, output_folder + '/map/walkways.shp')
    file.save_shapeFile(buildingUnits_shapeFile, output_folder + '/map/buildingUnits.shp')