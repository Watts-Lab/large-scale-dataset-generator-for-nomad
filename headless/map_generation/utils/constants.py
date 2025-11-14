
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