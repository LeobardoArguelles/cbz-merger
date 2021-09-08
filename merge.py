#!/usr/bin/python

import os
import cli.app
import cli.log
import logging
import re
from math import floor
from multiprocessing import Pool, Process
from time import sleep
from os import walk
from os import path
from zipfile import ZipFile
from shutil import copy2
from natsort import natsorted
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A5
from PyPDF2 import PdfFileMerger
from sys import exit

LOGGER = cli.log.CommandLineLogger(__name__)
LOGGER.addHandler(logging.StreamHandler())

# Directory with the extracted images, divided in folders
EXTRACT_DIR = '.extracted'

# Directory with the renamed images, all together, ready to zip
ZIP_DIR = 'zipper'

# Directory where original CBZ files are contained (the main directory)
# Will be set to the user provided parameter
main_dir = ''

# CPUs availables for parallel work
CPU_COUNT = os.cpu_count()

@cli.log.LoggingApp
def merge(app):

    # Set parameters
    LOGGER.setLevel(merge.params)

    global main_dir
    main_dir = merge.params.path

    # Try to move to the path provided
    try:
        os.chdir(main_dir)
    except FileNotFoundError as e:
        print('That path does not exist!')
        print('Use an absolute path, starting from "/"')
        raise e

    try:
        isPdf = True if merge.params.pdf else False

        # Extract zips
        pool = Pool(CPU_COUNT)
        makeDirectory(path.join('.', EXTRACT_DIR))
        zips = groupZips(os.listdir('.'), CPU_COUNT)
        pool.map(extractCbz, zips)

        # Rename / convert to pdf each extracted image
        makeDirectory(ZIP_DIR)
        dirs = groupDirs(os.listdir(path.join('.', EXTRACT_DIR)), CPU_COUNT)
        for i in range(len(dirs)):
            p = Process(target=mapExtractedImages, args=(dirs[i], isPdf, main_dir))
            p.start()
            p.join()

        mergeImages()

    except Exception as e:
        print(e)
        raise e


    print('\nAll done!')


def extractCbz(zips):
    """
    Extracts all zip (or cbz) archives found in dir, at
    the top level, to folders of the same name as the archive,
    locating them in a root folder called ".extracted"
    :param zips: List of the zip files to extract
    """

    # Extract cbz files and move them to their own folder, inside
    # <EXTRACT_DIR>
    for file in natsorted(zips):

        if file == EXTRACT_DIR or file == ZIP_DIR:
            continue

        name, ext = path.splitext(file)
        LOGGER.info('-'*50)
        extract_path = path.join(EXTRACT_DIR, name)
        makeDirectory(extract_path)

        LOGGER.info('Extracting: ' + name + '...')
        with ZipFile(file, 'r') as zipObj:
            zipObj.extractall(extract_path)


def renameImages():
    """
    Rename images extracted with extractCbz(). The default naming convention is
    <folderNumber>-<imgNumber>.<extension>, except if --volumize or
    --chapterize are requested. In those cases:
    --volumize: <Vol>-<imgNumber>
    --chapterize: TODO: Determine how this case should be handled.
    """

    makeDirectory(ZIP_DIR)

    topDir = os.getcwd()

    # if merge.params.volumize:
    for dir in natsorted(os.listdir(EXTRACT_DIR)):
        counter = 0
        currentDir = path.join(topDir, EXTRACT_DIR, dir)
        # Move images to ZIP_DIR, renaming them to be continuous
        for img in natsorted(os.listdir(currentDir)):
            name, ext = path.splitext(path.join(currentDir, img))

            LOGGER.info('-'*50)
            LOGGER.info('Renaming: ' + path.join(currentDir, img) + ' ---> ' + path.join(topDir, ZIP_DIR, dir + '-' + str(counter) + ext))
            counter += 1
            copy2(path.join(currentDir, img), path.join(topDir, ZIP_DIR, dir + '-' + str(counter) + ext))


def mergeImages():
    """
    Zips the renamed images, using the selected option:
    DEFAULT: Merge all the images in a single cbz archive.
    --volumize: Create one archive per volume, following the user provided regex e.g. 'Vol \d+'
    --chapterize: Create one archive for every <N> chapters, where <N> is indicated by the user.
    --maxsize: Create the necessary cbz archives, with the restriction that each one must have
                a size smaller than <M> (provided by the user).
    """
    topDir = os.getcwd()
    isPdf = askIfPdf()

    # File extension for generated zip files
    ARCHIVE_EXT = '.pdf' if isPdf else '.cbz'

    VOLS_DIR = path.join(topDir, 'zipped_volumes')
    makeDirectory(VOLS_DIR)

    IMGS_DIR = path.join(topDir, ZIP_DIR)
    os.chdir(IMGS_DIR)

    # Organize chapters by volume
    if merge.params.volumize:
        LOGGER.info('Starting to volumize chapters.')
        # Get stes of pre-sorted volumes keys, and all the images extracted
        volumes = getVolumes(IMGS_DIR)

        # Merge images by volume

        for volume, imgs in volumes.items():
            LOGGER.info('Archiving chapters of volume: ' + volume)
            currentArchive = path.join(VOLS_DIR, volume + ARCHIVE_EXT)
            """
            Working directory must be inside the images directory.
            Otherwise, the zipfile will have nested folders, e.g:
            /share
            |
             --- The World God Only Knows
                |
                |--- Vol 00-1.jpg
                |--- Vol 00-2.jpg
                |--- ...
                |--- Vol 99-99.jpg
            """
            p = Process(target=makeVolume, args=(currentArchive, isPdf, imgs))
            p.start()
            p.join()

    else:
        LOGGER.info('Creating archive...')
        ARCHIVE = path.join(topDir, merge.params.archive + ARCHIVE_EXT)
        if isPdf:
            # We will need to generate temp files and merge them.
            LOGGER.info('We will need to create some temporary pdfs...')
            queue = []
            counter = 0
            allImgs = natsorted(os.listdir('.'))
            # Cap open files at 1 000 to prevent errors
            imgsSets = segmentImgs(allImgs, 1000)

            # Create a temporary file per image set
            LOGGER.info('Creating temporary files')
            for imgs in imgsSets:
                temp = path.join(topDir, merge.params.archive + '-' + str(counter) + ARCHIVE_EXT)
                p = Process(target=makeTempPdf, args=(temp, imgs))
                p.start()
                p.join()
                counter += 1
                queue.append(temp)

            # Merge temporary files and clean up
            LOGGER.info('Now we can merge all temp files into our archive.')
            merger = PdfFileMerger()
            queueLength = len(queue)
            counter = 1
            for i in range(queueLength):
                LOGGER.info(f"Merging temp file [{counter}/{queueLength}]")

                # Append file
                currentFile = queue[i]
                merger.append(currentFile)

                counter += 1
            merger.write(ARCHIVE)
            merger.close()
            # Clean up temporary files
            while queue:
                os.remove(queue.pop())

        else:
            with ZipFile(ARCHIVE, 'w') as zf:
                for img in natsorted(os.listdir('.')):
                    LOGGER.debug('Adding: ' + img)
                    zf.write(path.join(root, img))



def segmentImgs(imgs, cap):
    """
    Segments imgs in n sets of maximum <cap> images.
    :param imgs: Full list of all images
    :param cap: Maximum number of images per set
    :return: List containing n sets of images, where n
            is how many sets of <cap> images can be created.
    """
    if len(imgs) <= cap:
       return [imgs]

    return [imgs[0:cap]] + segmentImgs(imgs[cap:], cap)

def getVolumes(dir):
    """
    Get the name of all the volumes located in <dir>, using the user-provided
    regex expression to identify them.
    Also, get a list of all the chapter's names, (also located in <dir>).
    :param dir: Path that points to the directory with all the renamed images.
    :return: A dictionary with volumes as keys, and a set of chapters as the value.
    """
    LOGGER.info('Getting dictionary of volumes and chapters')
    imgs = natsorted(os.listdir(dir))
    pat = re.compile(merge.params.volumize)
    currentVol = re.search(pat, imgs[0])[0]

    matches = list()
    volumes = dict()

    for img in imgs:
        imgVol = re.search(pat, img)[0]
        if imgVol == currentVol:
            matches.append(img)
            continue
        volumes[currentVol] = matches
        # Create a whole new list. Just clearing the same one causes problems,
        # because all the keys reference the same exact object
        matches = list()
        currentVol = imgVol
        # Don't forget this first image that changed the volume!
        matches.append(img)

    # Add the last volume, which is not assigned on the loop
    volumes[currentVol] = matches
    return volumes


def convertToPdf(img, destination, n):
    """
    Converts <img> to pdf. Store the pdf in
    the current directory
    :param img: Path to image to convert.
    :param destination: Full path to destination to save the pdf, but since
           reportlib only saves files in the working directory, <destination>
           is used only to know how to name the created pdf.
    :param n: A string indicating the current image number, for renaming and
              ordering purposes.
    """
    origname, ext = path.splitext(img)
    name = path.basename(destination) + '-' + n + '.pdf'
    w, h = A5

    LOGGER.info('-'*50)
    LOGGER.info('Converting: ' + origname + ' ---> ' + name)

    file = Canvas(name, pagesize=A5, pageCompression=merge.params.compression)
    file.drawImage(img, 0, 0, w, h)
    file.save()


def renameKeepExtension(origin, destination, n):
    """
    Moves image located in <origin> to <destination> directory, renaming it
    in the process.
    :param origin: Path to image to move and rename.
    :param destination: Path to destination directory
    :param n: A string indicating the current image number, for renaming and
              ordering purposes.
    """
    name, ext = path.splitext(origin)
    destname = path.basename(destination) + '-' + n + ext

    LOGGER.info('-'*50)
    LOGGER.info('Renaming: ' + name + ' ---> ' + destname)

    copy2(origin, path.join(destination + '-' + n + ext))


def mapExtractedImages(dirs, isPdf, main_dir):
    """
    Applies function <f> to every image in dirs.
    :param dirs: Collection of images to apply <f>
    :param isPdg: Indicates is user asked for pdf output
    :param main_dir: Top level dir where all files are located, as indicated by user
    """

    # f: Function to apply to each image
    if isPdf:
        f = convertToPdf
        os.chdir(path.join(main_dir, ZIP_DIR))
    else:
        f = renameKeepExtension

    for dir in natsorted(dirs):
        counter = 0
        currentDir = path.join(main_dir, EXTRACT_DIR, dir)
        # Move images to ZIP_DIR, renaming them to be continuous
        for img in natsorted(os.listdir(currentDir)):

            origin = path.join(currentDir, img)
            destination = path.join(main_dir, ZIP_DIR, dir)
            n = str(counter)


            f(origin, destination, n)

            counter += 1

    if isPdf:
        os.chdir(main_dir)


def makeDirectory(name):
    """
    Creates directory <name>, but only if it doesn't
    exist already.
    :param name: Directory to create
    """
    if not path.isdir(name):
        os.mkdir(name)


def groupZips(zips, n):
    """
    Makes <n> groups with equal number of files from the list of
    <zips> files provided.
    :param zips: List of files to be grouped
    :param n: Number of groups to make
    :return: List with <n> lists of files, where each list has the same
            number of files, if possible. The last group may have less
            files.
    """
    zips = natsorted(zips)
    length = len(zips)
    groupSize = floor(length / n)
    groups = []

    for i in range(0, length, groupSize):
        if i + groupSize == length:
            groups.append(zips[i:])
        else:
            groups.append(zips[i:i + groupSize])

    if i + groupSize < length - 1:
        groups.append(zips[i + groupSize:])

    return groups


def askIfPdf():
    """
    Checks if user asked for pdf outputs, which is denoted if merge.params.pdf
    is set to true.
    :return: True if user asked for pdf output, False otherwise
    """
    return merge.params.pdf


def makeTempPdf(path, imgs):
    """
    Creates a temporary pdf file to hold imgs. The idea is to use this function
    in parallel, so that several files get processed at once, and then they only
    have to be merged together on a single thread/core.
    :param path: Path to save the temp file to
    :param imgs: Pdf files of imgs to be merged
    """
    merger = PdfFileMerger()
    for img in imgs:
        merger.append(img)
    merger.write(path)
    merger.close()


def makeVolume(path, isPdf, imgs):
    """
    Create a single volume filled with <imgs>, and save it to <path>
    :param path: Path where to save the volume to
    :param isPdf: Indicates if the user requested pdf files or not
    :param imgs: Images to create volume with
    """

    if isPdf:
        merger = PdfFileMerger()
        for img in imgs:
            merger.append(img)
        merger.write(path)
        merger.close()
    else:
        with ZipFile(path, 'w') as zf:
            for img in imgs:
                LOGGER.debug('Adding: ' + img)
                zf.write(img)

# Alias
groupDirs = groupZips

# parameters
merge.add_param('path', help='path to your cbz archives', type=str)
merge.add_param('-a', '--archive', help='name of your compressed cbz file', type=str, default='CBZ_Archive')
merge.add_param('-vo', '--volumize', help='generate one archive per volume, using user provided regex', default=False, type=str)
merge.add_param('--pdf', help='output in pdf format', default=False, action="store_true")
# merge.add_param('--compression', help='pdf pages compression from 0 to 1', default=0.8)

if __name__ == "__main__":
    try:
        merge.run()
    except Exception as e:
        print(e)
        raise e
