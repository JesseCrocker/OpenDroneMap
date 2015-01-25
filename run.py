#!/usr/bin/env python

import argparse
import copy
import exifread
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
import shutil

class Image(object):
    def __init__(self, path, ccd=None, focal=None, resolution=(None, None)):
        super(Image, self).__init__()
        self.path = path
        self.ccd = ccd
        self.focal = focal
        self.resolution = resolution

    def max_dimension(self):
        return max(self.resolution[0], self.resolution[1])


def proccess_directory(path, options):
    logging.info("Proccessing directory: " + path)

    jobdir = os.path.join(path, "reconstruction-with-image-size-%i" % options['resize'])
    if not os.path.exists(jobdir):
        os.mkdir(jobdir)

    images = load_image_list(path, options)
    if len(images) == 0:
        logging.info("Found no usable images - Quiting")
        return

    max_width,min_width = sys.maxint,-sys.maxint-1
    max_height,min_height = sys.maxint,-sys.maxint-1
    for x in (image.resolution for image in images):
        min_width = min(x[0], min_width)
        max_width = max(x[0], max_width)
        min_height = min(x[1], min_height)
        max_height = max(x[1], max_height)

    if options['resize'] != 'orig':
        images = resize_images(options['resize'], jobdir, options, images)


def load_image_list(path, options):
    logging.info("Loading image metadata from %s" % path)
    ccd_defs_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ccd_defs.json')
    logging.debug("Reading CCD defs from " + ccd_defs_path)
    with open(ccd_defs_path, 'r') as f:
        ccd_defs = json.load(f)

    logging.info("Source files:")
    images = []
    for image_name in os.listdir(path):
        name, ext = os.path.splitext(image_name)
        if ext.lower() in ['.jpg', '.jpeg']:
            image_path = os.path.join(path, image_name)
            try:
                with open(image_path, 'rb') as fp:
                    tags = exifread.process_file(fp, details=False)

                image = Image(image_path)
                if 'Image GPSInfo' in tags:
                    #todo: extract gps
                    pass
                else:
                    logging.warning('Image does not have GPS tags')

                if 'force-ccd' in options:
                    image.ccd = options.force-ccd
                elif 'EXIF CCD Width' in tags:
                    image.ccd = float(str(tags['EXIF CCD Width']))
                elif 'Image Model' in tags:
                    camera = str(tags['Image Make']) + " " + str(tags['Image Model'])
                    if camera in ccd_defs:
                        image.ccd = ccd_defs[camera]
                    else:
                        raise Exception("CCD size for %s not in ccd_defs.json" % (camera))
                else:
                    raise Exception("Could not find ccd size")

                if 'force-focal' in options:
                    image.focal = options.force-focal
                elif 'EXIF FocalLength' in tags:
                    image.focal = float(str(tags['EXIF FocalLength']))
                else:
                    raise Exception("Focal length not found")

                if 'Image XResolution' in tags and 'Image YResolution' in tags:
                    image.resolution = (int(str(tags['Image XResolution'])), \
                        int(str(tags['Image YResolution'])))
                else:
                    pass
                    #todo open file and get resolution

                logging.info("using %s\tdimensions %ix%i / focal: %.1f mm / ccd: %.1fmm" % (image_name,\
                    image.resolution[0], image.resolution[1], image.ccd, image.focal))
                images.append(image)
            except Exception, e:
                logging.error("Error reading image " + image_path)
                logging.error(e)

    logging.info("loaded %i images", len(images))
    return images


def resize_images(max_dimension, jobdir, options, images):
    logging.info("Resize images to max dimension %d" % max_dimension)

    resized_images = []
    for image in images:
        image_dir, name = os.path.split(image.path)

        resized_image = copy.copy(image)
        resized_image.path = os.path.join(jobdir, name)

        if image.max_dimension() < max_dimension:
            logging.debug("Not resizing image %s" % name)
            shutil.copy(image.path, resized_image.path)
            resized_images.append(image)
        else:
            run('convert -resize %ix%i -quality 100 %s %s' % \
                (max_dimension, max_dimension, image.path, resized_image.path))
        
            with open(resized_image.path, 'rb') as fp:
                tags = exifread.process_file(fp, details=False)

            if 'Image XResolution' in tags and 'Image YResolution' in tags:
                resized_image.resolution = (int(str(tags['Image XResolution'])), \
                    int(str(tags['Image YResolution'])))
            else:
                resized_image.resolution = (None, None)
                logging.error("Error getting size for resized image")

            logging.info("Resize %s\tto%s\t(%i x %i)" % \
                (name, resized_image.path, resized_image.resolution[0], resized_image.resolution[1]))
        resized_images.append(resized_image)

    return resized_images


def run(command):
    logging.debug(command)
    try:
        output = subprocess.check_call(command, shell=True)
        logging.debug(output)
    except subprocess.CalledProcessError, e:
        logging.error("Command failed with return code %i" % e.returncode)
        logging.error(e.output)
        return False
    else:
        return True

#arg parser validators
def positive_or_orig(value):
    if value == 'orig':
        return 'orig'
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError("%s is an invalid positive int value" % value)
    return ivalue


def positive_int(value):
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError("%s is an invalid positive int value" % value)
    return ivalue


def float_plus_or_minus_one(value):
    fvalue = float(value)
    if fvalue < -1 or fvalue > 1:
        raise argparse.ArgumentTypeError("%s is an invalid value, valid values are -1 to 1" % value)
    return fvalue


def positive_float(value):
    fvalue = float(value)
    if fvalue < 0:
        raise argparse.ArgumentTypeError("%s is an invalid value for a positive float" % value)
    return fvalue


def float_greater_than_one(value):
    fvalue = float(value)
    if fvalue < 1:
        raise argparse.ArgumentTypeError("%s is an invalid value, valid values are >= 1" % value)
    return fvalue


def _main():
    action_choices = ['resize', 'getKeypoints', 'match', 'bundler', 'cmvs', 'pmvs',\
         'odm_meshing', 'odm_texturing', 'odm_georeferencing', 'odm_orthophoto']

    parser = argparse.ArgumentParser(description='...',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('--match-size', default=200, type=int)
    parser.add_argument('--resize-to', default=1200, type=positive_or_orig,
        dest='resize',
        metavar='<positive int> | orig',
        help='''
will resize the images so that the maximum width/height of the images are 
smaller or equal to the specified number if "--resize-to orig" is used it 
will use the images without resizing
        ''')
    
    parser.add_argument('--start-with', default='resize', choices=action_choices,
        help='will start the sript at the specified step')
    parser.add_argument('--ends-with', default='odm_texturing', choices=action_choices,
        help='will stop the sript after the specified step')
    parser.add_argument('--run-only', choices=action_choices,
        help='''
will only execute the specified step. equal to --start-with <step> --end-with <step>
        ''')

    parser.add_argument('--cmvs-maxImages', default=100, type=positive_int,
        metavar='<positive integer>',
        help='the maximum number of images per cluster')
    
    parser.add_argument("--matcher-ratio", default=0.6, type=float,
        metavar='<float>',
        help='ratio of the distance to the next best matched keypoint')
    parser.add_argument("--matcher-threshold", default=2.0, type=float,
        metavar='<float> (percent)',
        help='''
ignore matched keypoints if the two images share less then <float> percent of keypoints
        ''')
    
    parser.add_argument("--pmvs-level", default=1, type=positive_int,
        metavar='<positive integer>')
    parser.add_argument("--pmvs-csize", default=2, type=positive_int,
        metavar='<positive integer>')
    parser.add_argument("--pmvs-threshold", default=0.7, type=float_plus_or_minus_one,
        metavar='<float: -1.0 <= x <= 1.0>')
    parser.add_argument("--pmvs-wsize", default=7, type=positive_int,
        metavar='<positive integer>')
    parser.add_argument("--pmvs-minImageNum", default=3, type=positive_int,
        metavar='<positive integer>',
        help='''
see http://grail.cs.washington.edu/software/pmvs/documentation.html for 
an explanation of these parameters
        ''')

    parser.add_argument("--odm_meshing-maxVertexCount", default=100000, type=positive_int,
        metavar='<positive integer>',
        help='The maximum vertex count of the output mesh.')
    parser.add_argument("--odm_meshing-octreeDepth", default=9, type=positive_int,
        metavar='<positive integer>',
        help='''
Octree depth used in the mesh reconstruction, increase to get more vertices, 
recommended values are 8-12
        ''')
    parser.add_argument("--odm_meshing-samplesPerNode", default=1, type=float_greater_than_one,
        metavar='<float: 1.0 <= x>',
        help='''
Number of points per octree node, recommended value: 1.0
        ''')

    parser.add_argument("--odm_meshing-solverDivide", default=9, type=int)

    parser.add_argument("--odm_texturing-textureResolution", default=4096, type=positive_int)
    parser.add_argument("--odm_texturing-textureWithSize", default=600, type=positive_int)

    parser.add_argument("--force-focal", type=positive_float,
        metavar='<positive float>',
        help='override the focal length information for the images')
    parser.add_argument('--force-ccd', type=positive_float,
        metavar='<positive float>',
        help='override the ccd width information for the images')

    parser.add_argument('directory', nargs='*', default=[os.getcwd(),])

    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(message)s',
        level=logging.DEBUG if args.verbose else
        (logging.ERROR if args.quiet else logging.INFO))
    logging.debug("configuration:")
    logging.debug(json.dumps(vars(args), sort_keys=True, indent=4, separators=(',', ': ')))

    for path in args.directory:
        if os.path.exists(path):
            proccess_directory(path, vars(args))
        else:
            logging.error("Path %s does not exist" % path)

if __name__ == "__main__":
    _main()
