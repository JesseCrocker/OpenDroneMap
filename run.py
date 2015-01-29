#!/usr/bin/env python

import argparse
import copy
from datetime import datetime
import exifread
import json
import logging
from multiprocessing.pool import ThreadPool
import os
import re
import shutil
import subprocess
import sys

class Image(object):
    def __init__(self, path, ccd=None, focal=None, resolution=(None, None)):
        super(Image, self).__init__()
        self.path = path
        self.ccd = ccd
        self.focal = focal
        self.resolution = resolution
        self.working_path = None
        file_path, file_name = os.path.split(path)
        self.file_name = file_name

    def max_dimension(self):
        return max(self.resolution[0], self.resolution[1])


class StepResult(object):
    def __init__(self, name=None):
        super(StepResult, self).__init__()
        self.start_time = datetime.now()
        self.end_time = None
        self.name = name


    def end(self, success=False, logs=None):
        self.end_time = datetime.now()
        self.success = success
        self.logs = logs

    def duration(self):
        return self.end_time - self.start_time

    def __str__(self):
        return "%s in %s success:%s" %(self.name, self.duration(), self.success)


def proccess_directory(path, options):
    logging.info("Proccessing directory: " + path)
    steps_to_run = options['steps_to_run']
    logging.debug("Planning to run steps " + ", ".join(steps_to_run))

    step_results = []

    result = StepResult(name="load_image_list")
    images = load_image_list(path, options)
    result.end(len(images) > 0)
    logging.info(result)
    step_results.append(result)
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

    for step in steps_to_run:
        result = StepResult(name=step)
        step_function = step_functions[step]
        success, logs = step_function(options, images)
        result.end(success=success, logs=logs)
        step_results.append(result)
        logging.info(result)
        if not success:
            logging.error("Step %s failed, stopping" % step)
            break


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

                #this seems to frequently be wrong
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

# Steps 
def resize_images(options, images):
    logging.info(' - running resize - ')

    work_dir = options['work_dir']
    max_dimension = options['resize']
    logging.debug("Resize images to max dimension %d" % max_dimension)

    jobs = []
    for image in images:
        jobs.append((image, work_dir, max_dimension))

    pool = ThreadPool(processes=options['thread_count'])
    try:
        pool.map(_resize_image, jobs)
    except:
        return False, None
    else:
        return True, None


def _resize_image(args):
    image, jobdir, max_dimension = args

    image_dir, name = os.path.split(image.path)

    image.working_path = os.path.join(jobdir, name)

    if max_dimension == 'orig' or image.max_dimension() < max_dimension:
        logging.debug("Not resizing image %s" % name)
        shutil.copy(image.path, image.working_path)
    else:
        run('convert -resize %ix%i -quality 100 %s %s' % \
            (max_dimension, max_dimension, image.path, image.working_path))
        
        with open(image.working_path, 'rb') as fp:
            tags = exifread.process_file(fp, details=False)

        #this seems to frequently be wrong
        if 'Image XResolution' in tags and 'Image YResolution' in tags:
            image.resolution = (int(str(tags['Image XResolution'])), \
                int(str(tags['Image YResolution'])))
        else:
            image.resolution = (None, None)
            logging.error("Error getting size for resized image")

        logging.info("Resize %s\tto %s\t(%i x %i)" % \
            (name, image.working_path, image.resolution[0], image.resolution[1]))


def get_keypoints(options, images):
    logging.info(' - finding keypoints - ')
    return True, None

def match(options, images):
    logging.info(' - matching keypoints - ')
    return True, None


def bundler(options, images):
    logging.info(' - running bundler - ')
    return True, None


def cmvs(options, images):
    logging.info(' - running cmvs - ')
    return True, None


def pmvs(options, images):
    logging.info(' - running pmvs - ')
    return True, None


def odm_meshing(options, images):
    logging.info(' - running odm_meshing - ')
    return True, None


def odm_texturing(options, images):
    logging.info(' - running odm_texturing - ')
    return True, None


def odm_georeferencing(options, images):
    logging.info(' - running odm_georeferencing - ')
    return True, None


def odm_orthophoto(options, images):
    logging.info(' - runnng odm_orthophoto - ')
    return True, None


step_functions = {
    "resize" : resize_images,
    "getKeypoints": get_keypoints,
    "match": match,
    "bundler": bundler,
    "cmvs": cmvs,
    "pmvs": pmvs,
    "odm_meshing": odm_meshing,
    "odm_texturing": odm_texturing,
    "odm_georeferencing": odm_georeferencing,
    "odm_orthophoto": odm_orthophoto
}


# Util
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


def default_thread_count():
    #linux
    if os.path.exists('/sys/devices/system/cpu/'):
        dir_entries = os.path.listdir('/sys/devices/system/cpu/')
        if len(dir_entries) > 0:
            return len(dir_entries)

    #OS X/BSD
    try:
        output = subprocess.check_call(['sysctl', '-n', 'hw.ncpu'])
        logging.debug(output)
    except subprocess.CalledProcessError, e:
        pass

    return 2


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

def existing_directory(value):
    if not os.path.exists(value):
        raise argparse.ArgumentTypeError("%s does not exists" % value)
    if not os.path.isdir(value):
        raise argparse.ArgumentTypeError("%s is not a directory" % value)
    return value


#

def _main():
    all_steps = ['resize', 'getKeypoints', 'match', 'bundler', 'cmvs', 'pmvs',\
         'odm_meshing', 'odm_texturing', 'odm_georeferencing', 'odm_orthophoto']

    parser = argparse.ArgumentParser(description='...',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-j', '--jobs', type=positive_int, dest='thread_count')

    parser.add_argument('--match-size', default=200, type=int)
    parser.add_argument('--resize-to', default=1200, type=positive_or_orig,
        dest='resize',
        metavar='<positive int> | orig',
        help='''
will resize the images so that the maximum width/height of the images are 
smaller or equal to the specified number if "--resize-to orig" is used it 
will use the images without resizing
        ''')
    
    parser.add_argument('--start-with', default='resize', choices=all_steps,
        dest='start_with',
        help='will start the sript at the specified step')
    parser.add_argument('--end-with', default='odm_texturing', choices=all_steps,
        dest='end_with',
        help='will stop the sript after the specified step')
    parser.add_argument('--run-only', choices=all_steps, dest='run_only',
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

    parser.add_argument('--work-dir', dest='work_dir',
        help='''
Directory to store working files in. Defaults to source/reconstruction-with-image-size-<resize>
        ''')

    parser.add_argument('--results-dir', dest='results_dir',
        help='''
Directory to store results in. Defaults to source/reconstruction-with-image-size-<resize>-results
        ''')

    parser.add_argument('--bin-dir', dest='bin_dir', type=existing_directory,
        help='''
Directory where ODM binaries are located.
        ''', 
        default=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'bin') )
    
    parser.add_argument('directory', nargs='*', default=[os.getcwd(),], 
        type=existing_directory)

    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(message)s',
        level=logging.DEBUG if args.verbose else
        (logging.ERROR if args.quiet else logging.INFO))

    if args.thread_count is None:
        args.thread_count = default_thread_count()
    args_dict = vars(args)

    steps_to_run = []
    if 'run_only' in args_dict and args_dict['run_only'] is not None:
        steps_to_run = [args_dict['run_only'],]
    else:
        if 'start_with' in args_dict and 'ends_with' in args_dict:
            copy_steps = False
            for step in all_steps:
                if 'start_with' in args_dict and step == args_dict['start_with']:
                    copy_steps = True
                if copy_steps:
                    steps_to_run.append(step)
                if 'end_with' in args_dict and step == args_dict['end_with']:
                    break
        else:
            steps_to_run = all_steps

    args_dict['steps_to_run'] = steps_to_run

    logging.debug("configuration:")
    logging.debug(json.dumps(args_dict, sort_keys=True, indent=4, separators=(',', ': ')))

    set_work_dir = args_dict['work_dir'] is None
    set_results_dir = args_dict['results_dir'] is None

    for path in args.directory:
        if set_work_dir:
            args_dict['work_dir'] = os.path.join(path, "reconstruction-with-image-size-%i" % \
                args_dict['resize'])
        if not os.path.exists(args_dict['work_dir']):
            os.mkdir(args_dict['work_dir'])

        if set_results_dir:
            args_dict['results_dir'] = os.path.join(path, "reconstruction-with-image-size-%i-results" % \
                args_dict['resize'])
        if not os.path.exists(args_dict['results_dir']):
            os.mkdir(args_dict['results_dir'])

        proccess_directory(path, args_dict)


if __name__ == "__main__":
    _main()
