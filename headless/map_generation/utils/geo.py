from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError


# Pre-defined bounding boxes for common cities
PREDEFINED_BOUNDING_BOXES = {
    'atl-metro': [-84.5505285, 33.64708314, -84.28945431, 33.88663263],
    'atl': [-84.41213984, 33.72878582, -84.36418537, 33.76304255],
    'atlanta': [-84.41213984, 33.72878582, -84.36418537, 33.76304255],
    'bjng': [116.1632651, 39.7831364, 116.6294095, 40.039197],
    'beijing': [116.1632651, 39.7831364, 116.6294095, 40.039197],
    'brln': [13.3656432, 52.5066516, 13.4174008, 52.5323714],
    'berlin': [13.3656432, 52.5066516, 13.4174008, 52.5323714],
    'gmu': [-77.31851683, 38.82516657, -77.29851636, 38.83568792],
    'nola': [-90.0747321, 29.94990921, -90.04599532, 29.96606048],
    'new orleans': [-90.0747321, 29.94990921, -90.04599532, 29.96606048],
    'sfco': [-122.51419799, 37.70829506, -122.35784432, 37.8108725],
    'san francisco': [-122.51419799, 37.70829506, -122.35784432, 37.8108725],
    'test': [-84.41213984, 33.72878582, -84.39418537, 33.73304255],
}


def geocode_city(city_name, timeout=10):
    """
    Geocode a city name to get its bounding box using OpenStreetMap Nominatim.
    
    Parameters
    ----------
    city_name : str
        Name of the city (e.g., "Philadelphia, PA", "Tokyo, Japan")
    timeout : int
        Timeout in seconds for the geocoding request
    
    Returns
    -------
    list or None
        Bounding box as [min_lon, min_lat, max_lon, max_lat], or None if not found
    """
    try:
        geolocator = Nominatim(user_agent="nomad_datagen")
        location = geolocator.geocode(city_name, timeout=timeout)
        
        if location is None:
            print(f"Could not find location: {city_name}")
            return None
        
        # Get the bounding box from the raw response
        # Nominatim returns boundingbox as [south, north, west, east] (strings)
        if hasattr(location, 'raw') and 'boundingbox' in location.raw:
            bb = location.raw['boundingbox']
            # Convert to [min_lon, min_lat, max_lon, max_lat] format
            min_lat, max_lat, min_lon, max_lon = [float(x) for x in bb]
            bounding_box = [min_lon, min_lat, max_lon, max_lat]
            print(f"Found bounding box for '{city_name}': {bounding_box}")
            return bounding_box
        else:
            print(f"No bounding box available for: {city_name}")
            return None
            
    except GeocoderTimedOut:
        print(f"Geocoding timed out for: {city_name}")
        return None
    except GeocoderServiceError as e:
        print(f"Geocoding service error for {city_name}: {e}")
        return None
    except Exception as e:
        print(f"Error geocoding {city_name}: {e}")
        return None


def get_bounding_box(map_name, use_geocoding=True):
    """
    Get a bounding box for a city or location.
    
    First checks pre-defined cities, then falls back to geocoding if enabled.
    
    Parameters
    ----------
    map_name : str
        Name of the city or location. Can be:
        - A pre-defined shorthand (e.g., 'atl', 'nola', 'sfco')
        - A full city name (e.g., 'Philadelphia, PA', 'Tokyo, Japan')
    use_geocoding : bool
        If True, use Nominatim geocoding for unknown cities (default: True)
    
    Returns
    -------
    list
        Bounding box as [min_lon, min_lat, max_lon, max_lat]
    
    Raises
    ------
    ValueError
        If the city cannot be found and geocoding fails
    
    Examples
    --------
    >>> get_bounding_box('atlanta')  # Pre-defined
    [-84.41213984, 33.72878582, -84.36418537, 33.76304255]
    
    >>> get_bounding_box('Philadelphia, PA')  # Geocoded
    [-75.2803..., 39.8670..., -74.9558..., 40.1379...]
    
    >>> get_bounding_box('Tokyo, Japan')  # Geocoded
    [138.9427..., 35.5209..., 139.9188..., 35.8984...]
    """
    # Normalize the map name for lookup
    map_name_lower = map_name.lower().strip()
    
    # Check pre-defined bounding boxes first
    if map_name_lower in PREDEFINED_BOUNDING_BOXES:
        bbox = PREDEFINED_BOUNDING_BOXES[map_name_lower]
        print(f"Using pre-defined bounding box for '{map_name}': {bbox}")
        return bbox
    
    # Try geocoding if enabled
    if use_geocoding:
        print(f"'{map_name}' not in pre-defined cities, attempting geocoding...")
        bbox = geocode_city(map_name)
        if bbox is not None:
            return bbox
    
    # Raise error if we couldn't find the city
    raise ValueError(
        f"Could not find bounding box for '{map_name}'. "
        f"Pre-defined cities: {list(PREDEFINED_BOUNDING_BOXES.keys())}"
    )