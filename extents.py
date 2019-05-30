#!/usr/bin/env python3

from osgeo import gdal,ogr,osr
import os
import json
import click
import sys

# Stolen from https://gis.stackexchange.com/questions/57834/how-to-get-raster-corner-coordinates-using-python-gdal-bindings

def GetExtent(gt, cols, rows):
    ''' Return list of corner coordinates from a geotransform

        @type gt:   C{tuple/list}
        @param gt: geotransform
        @type cols:   C{int}
        @param cols: number of columns in the dataset
        @type rows:   C{int}
        @param rows: number of rows in the dataset
        @rtype:    C{[float,...,float]}
        @return:   coordinates of each corner
    '''
    ext=[]
    xarr=[0,cols]
    yarr=[0,rows]

    for px in xarr:
        for py in yarr:
            x=gt[0]+(px*gt[1])+(py*gt[2])
            y=gt[3]+(px*gt[4])+(py*gt[5])
            ext.append([x,y])
        yarr.reverse()
    return ext

def ReprojectCoords(coords, src_srs, tgt_srs):
    ''' Reproject a list of x,y coordinates.

        @type geom:     C{tuple/list}
        @param geom:    List of [[x,y],...[x,y]] coordinates
        @type src_srs:  C{osr.SpatialReference}
        @param src_srs: OSR SpatialReference object
        @type tgt_srs:  C{osr.SpatialReference}
        @param tgt_srs: OSR SpatialReference object
        @rtype:         C{tuple/list}
        @return:        List of transformed [[x,y],...[x,y]] coordinates
    '''
    trans_coords=[]
    transform = osr.CoordinateTransformation(src_srs, tgt_srs)
    for x,y in coords:
        x,y,z = transform.TransformPoint(x,y)
        trans_coords.append([x,y])
    return trans_coords

def get_min_max(extents, buffer):
    minx = sys.float_info.max
    maxx = sys.float_info.min
    miny = sys.float_info.max
    maxy = sys.float_info.min
    for coord in extents:
        x = coord[0]
        y = coord[1]
        if x > maxx:
            maxx = x
        if x < minx:
            minx = x
        if y > maxy:
            maxy = y
        if y < miny:
            miny = y

    return map(str, (minx - buffer, miny - buffer, maxx + buffer, maxy + buffer))


@click.command(help="\b Get extents for a GDAL readable file.")
@click.option('--in_file', '-i', required=True, help="Input file")
@click.option('--out_file', '-o', default="extent.json", required=False, help="Output file")
@click.option('--sourcesrs', '-s', required=False, help="Set the source srs to convert from", type=int)
@click.option('--targetsrs', '-t', default=26911, help="Target srs to convert to", type=int)
def main(in_file, out_file, sourcesrs, targetsrs):
    print("Starting.")
    if not os.path.exists(in_file):
        print("Failed to find the file.")
        return

    ds=gdal.Open(in_file)

    gt=ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize
    ext=GetExtent(gt, cols, rows)

    src_srs = osr.SpatialReference()
    tgt_srs = osr.SpatialReference()

    if sourcesrs:
        src_srs.ImportFromEPSG(sourcesrs)
    else:
        src_srs.ImportFromWkt(ds.GetProjection())
    # print("Source SRS is: {}".format(src_srs))

    if targetsrs:
        tgt_srs.ImportFromEPSG(targetsrs)
    else:
        tgt_srs = src_srs.CloneGeogCS()

    geo_ext = ReprojectCoords(ext, src_srs, tgt_srs)

    with open(out_file, 'w') as outfile:
        json.dump(geo_ext, outfile)

    print(" ".join(get_min_max(geo_ext, 0.001)))
    print("Finished.")


if __name__ == "__main__":
    main()