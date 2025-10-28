import utils.pqgis as pqgis

if __name__ == '__main__':
    
    # bounding_box = [ -93.37271616619313, 44.87995237885596, -93.18917592484306, 45.065984365649186]
    bounding_box = [-75.280266, 39.867004, -74.955763, 40.137992]
    output_folder = 'pol/maps/philadelphia'

    pqgis.generate_map(bounding_box, output_folder, new_map=True)

    print('Map generated successfully!')