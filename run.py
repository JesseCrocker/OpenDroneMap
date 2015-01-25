#!/usr/bin/env python

import argparse
import logging
import json
import os
import exifread
import re

def proccess_directory(path, options):
    logging.info("Proccessing directory: " + path)
    images = load_image_list(path, options)

def load_image_list(path, options):
    ccd_defs_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ccd_defs.json')
    logging.debug("Reading CCD defs from " + ccd_defs_path)
    with open(ccd_defs_path, 'r') as f:
        ccd_defs = json.load(f)

    logging.info("Source files:")
    for image_path in os.listdir(path):
        name, ext = os.path.splitext(image_path)
        if ext.lower() in ['.jpg', '.jpeg']:
            logging.debug(image_path)
            image_path = os.path.join(path, image_path)
            with open(image_path, 'rb') as fp:
                tags = exifread.process_file(fp, details=False)
            #logging.debug(tags)
            
def _main():
    action_choices = ['resize', 'getKeypoints', 'match', 'bundler', 'cmvs', 'pmvs',\
         'odm_meshing', 'odm_texturing', 'odm_georeferencing', 'odm_orthophoto']

    parser = argparse.ArgumentParser(description='...',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('--match-size', default=200, type=int)
    parser.add_argument('--resize-to', default=1200, type=int, help="""
will resize the images so that the maximum width/height of the images are 
smaller or equal to the specified number if "--resize-to orig" is used it 
will use the images without resizing
        """)
    
    parser.add_argument('--start-with', default='resize', choices=action_choices,
        help='will start the sript at the specified step')
    parser.add_argument('--ends-with', default='odm_texturing', choices=action_choices,
        help='will stop the sript after the specified step')
    parser.add_argument('--run-only', choices=action_choices,
        help='''
will only execute the specified step. equal to --start-with <step> --end-with <step>
        ''')

    parser.add_argument('--cmvs-maxImages', default=100, type=int,
        metavar='<positive integer',
        help='the maximum number of images per cluster')
    
    parser.add_argument("--matcher-ratio", default=0.6, type=float,
        metavar='<float>',
        help='ratio of the distance to the next best matched keypoint')
    parser.add_argument("--matcher-threshold", default=2.0, type=float,
        metavar='<float> (percent)',
        help='''
ignore matched keypoints if the two images share less then <float> percent of keypoints
        ''')
    
    parser.add_argument("--pmvs-level", default=1, type=int,
        metavar='<positive integer>')
    parser.add_argument("--pmvs-csize", default=2, type=int,
        metavar='<positive integer>')
    parser.add_argument("--pmvs-threshold", default=0.7, type=float,
        metavar='<float: -1.0 <= x <= 1.0>')
    parser.add_argument("--pmvs-wsize", default=7, type=int,
        metavar='<positive integer>')
    parser.add_argument("--pmvs-minImageNum", default=3, type=int,
        metavar='<positive integer',
        help='''
see http://grail.cs.washington.edu/software/pmvs/documentation.html for an explanation of these parameters
        ''')

    parser.add_argument("--odm_meshing-maxVertexCount", default=100000, type=int,
        metavar='<positive integer>',
        help='The maximum vertex count of the output mesh.')
    parser.add_argument("--odm_meshing-octreeDepth", default=9, type=int,
        metavar='<positive integer>',
        help='''
Octree depth used in the mesh reconstruction, increase to get more vertices, 
recommended values are 8-12
        ''')
    parser.add_argument("--odm_meshing-samplesPerNode", default=1, type=float,
        metavar='<float: 1.0 <= x>',
        help='''
Number of points per octree node, recommended value: 1.0
        ''')

    parser.add_argument("--odm_meshing-solverDivide", default=9, type=int)

    parser.add_argument("--odm_texturing-textureResolution", default=4096, type=int)
    parser.add_argument("--odm_texturing-textureWithSize", default=600, type=int)

    parser.add_argument("--force-focal", type=float,
        metavar='<positive float>',
        help='override the focal length information for the images')
    parser.add_argument('--force-ccd', type=float,
        metavar='<positive float>',
        help='override the ccd width information for the images')

    parser.add_argument('directory', nargs='*', default=[os.getcwd(),])

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else
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
