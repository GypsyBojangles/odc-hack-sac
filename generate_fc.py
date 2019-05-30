import datacube
import rasterio.merge
import os
from datacube.storage import masking
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from datacube.model import Measurement
from datacube.helpers import write_geotiff
from fc.fractional_cover import fractional_cover
from shapely.geometry import box

import warnings
dc = datacube.Datacube(app='fc')

footprint = box(583785.0,-2036115.0, 814515.0, -1802085.0)
query = {'time': ('2016-09-16', '2016-09-18')}
query['crs'] = 'EPSG:32660'
query['resolution'] = (-30, 30)
query['output_crs'] = 'EPSG:32660'
query['product']= 'ls8_usgs_sr_scene'
filename='fc/ls8_fc_'
fishnet_size = 1500000
bands_of_interest = ['green','red','nir','swir1','swir2']
overview_resampling = 'nearest'

sensor_regression_coefficients= {
  'blue':[0.00041,0.97470],
  'green':[0.00289,0.99779],
  'red':[0.00274,1.00446],
  'nir':[0.00004,0.98906],
  'swir1':[0.00256,0.99467],
  'swir2':[-0.00327,1.02551]
}

dataset_constants = {
    'product_type':'ls8_usgs_fc_scene',
    'format':{'name':'GeoTIFF'},
    'lineage':{'source_datasets': {}}
}


fc_measurements = [
    Measurement(name='BS',units='percent',dtype='int16',nodata=-1),
    Measurement(name='PV',units='percent',dtype='int16',nodata=-1),
    Measurement(name='NPV',units='percent',dtype='int16',nodata=-1),
    Measurement(name='UE',units='1',dtype='int16',nodata=-1)]

def fishnet(geometry, threshold):
    bounds = geometry.bounds
    xmin = int(bounds[0] // threshold)
    xmax = int(bounds[2] // threshold)
    ymin = int(bounds[1] // threshold)
    ymax = int(bounds[3] // threshold)
    ncols = int(xmax - xmin + 1)
    nrows = int(ymax - ymin + 1)
    result = []
    for i in range(xmin, xmax+1):
        for j in range(ymin, ymax+1):
            b = box(i*threshold, j*threshold, (i+1)*threshold, (j+1)*threshold)
            g = geometry.intersection(b)
            if g.is_empty:
                continue
            result.append(g)
    return result

def create_cog(input, output, overview_resampling, bidx):
    cogeo_profile = 'deflate'
    nodata = -1
    overview_level = 6
    overview_resampling = overview_resampling
    threads = 8
    output_profile = cog_profiles.get(cogeo_profile)
    output_profile.update(dict(BIGTIFF=os.environ.get("BIGTIFF", "IF_SAFER")))
    block_size = min(
        int(output_profile["blockxsize"]), int(output_profile["blockysize"])
    )

    config = dict(
        NUM_THREADS=threads,
        GDAL_TIFF_INTERNAL_MASK=os.environ.get("GDAL_TIFF_INTERNAL_MASK", True),
        GDAL_TIFF_OVR_BLOCKSIZE=os.environ.get("GDAL_TIFF_OVR_BLOCKSIZE", block_size),
    )

    cog_translate(
        src_path=input,
        dst_path=output,
        dst_kwargs=output_profile,
        indexes=bidx,
        nodata=nodata,
        web_optimized=False,
        add_mask=False,
        overview_level=overview_level,
        overview_resampling=overview_resampling,
        config=config,
        quiet=False
    )

def load_and_generate_fc(query):
    sr = dc.load(measurements = bands_of_interest,
                 group_by='solar_day', 
                 **query).squeeze()
    if not sr:
        return None

    warnings.filterwarnings('ignore')
    fc = fractional_cover(sr, fc_measurements, sensor_regression_coefficients)
    warnings.filterwarnings('always')

    del sr

    return fc

def write_fc_band_tile(fc, key, filename):
    slim_dataset = fc[[key]]  # create a one band dataset
    attrs = slim_dataset[key].attrs.copy()  # To get nodata in
    del attrs['crs']  # It's format is poor
    del attrs['units']  # It's format is poor
    slim_dataset[key] = fc.data_vars[key].astype('int16', copy=True)
    output_filename = filename+key+'_'+str(tile_no)+'_TEMP'+'.tif'
    write_geotiff(output_filename, slim_dataset, profile_override=attrs)
    return output_filename

def combine_tiles_to_scene(fc_tiles_locations,key,filename):
    files = fc_tiles_locations[key]
    output_filename = filename+key+'_TEMP'+'.tif'
    sources = [rasterio.open(path) for path in files]
    dest, out_transform = rasterio.merge.merge(sources)

    with rasterio.open(files[0]) as src:
        profile = src.profile

    profile['transform'] = out_transform
    profile['width'] = len(dest[0][0])
    profile['height'] = len(dest[0])

    with rasterio.open(output_filename, 'w', **profile) as dst:
        dst.write(dest.astype(rasterio.int16))

    [os.remove(path) for path in files]
    return output_filename

tile_no = 0
fc_tiles_locations = {}
bounds_list = fishnet(footprint,fishnet_size)
for measurement in fc_measurements:
    fc_tiles_locations[measurement['name']] = []

for bb in bounds_list:
    query['x'] = (bb.bounds[0],bb.bounds[2])
    query['y'] = (bb.bounds[1],bb.bounds[3])

    fc = load_and_generate_fc(query)
    if fc:
        for measurement in fc_measurements:
            key = measurement['name']
            fc_tiles_locations[key].append(write_fc_band_tile(fc,key,filename))
        tile_no = tile_no + 1
        del fc

for measurement in fc_measurements:
    key = measurement['name']
    uncogged_output_file = combine_tiles_to_scene(fc_tiles_locations,key,filename)
    target_filename = filename+key+'.tif'
    #as we have created this bands separately, band index (bidx) is always 0
    bidx = 0
    create_cog(uncogged_output_file, target_filename, overview_resampling, bidx)
    os.remove(uncogged_output_file)


