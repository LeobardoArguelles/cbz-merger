#!/usr/bin/python

import os
import cli.app
import cli.log
import logging
import re
from time import sleep
from os import walk
from os import path
from zipfile import ZipFile
from shutil import copy2
from natsort import natsorted
from sys import exit

LOGGER = cli.log.CommandLineLogger(__name__)
LOGGER.addHandler(logging.StreamHandler())

# Directory with the extracted images, divided in folders
EXTRACT_DIR = '.extracted'

# Directory with the renamed images, all together, ready to zip
ZIP_DIR = 'zipper'

# File extension for generated zip files
ARCHIVE_EXT = '.cbz'

@cli.log.LoggingApp
def merge(app):
    LOGGER.setLevel(merge.params)

    # Try to move to the path provided
    try:
        os.chdir(merge.params.path)
    except FileNotFoundError as e:
        print('That path does not exist!')
        print('Use an absolute path, starting from "/"')
        raise e

    # extractCbz(merge.params.path)
    if merge.params.pdf:
        convertToPdf()
    else:
        renameImages()

    mergeImages()

    print('\nAll done!')


def extractCbz(dir):
    """
    Extracts all zip (or cbz) archives found in dir, at
    the top level, to folders of the same name as the archive,
    locating them in a root folder called ".extracted"
    :param dir: Directory containing the zip files.
    """
    makeDirectory(path.join('.'), EXTRACT_DIR)

    # Extract cbz files and move them to their own folder, inside
    # <EXTRACT_DIR>
    for file in natsorted(os.listdir('.')):

        if file == EXTRACT_DIR or file == ZIP_DIR:
            continue

        name, ext = path.splitext(file)
        LOGGER.info('-'*50)
        extract_path = path.join(EXTRACT_DIR, name)
        makeDirectory(extract_path)

        LOGGER.info('Extracting: ' + name + '...')
        with ZipFile(file, 'r') as zipObj:
            zipObj.extractall(extract_path)
        LOGGER.info('-'*50)


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

    if merge.params.volumize:
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
                LOGGER.info('-'*50)
    # TODO: Refractor to not reuse code. There must be a smarter way to do this.
    else:
        dirCounter = 0
        for dir in natsorted(os.listdir(EXTRACT_DIR)):
            counter = 0
            currentDir = path.join(topDir, EXTRACT_DIR, dir)
            # Move images to ZIP_DIR, renaming them to be continuous
            for img in natsorted(os.listdir(currentDir)):
                name, ext = path.splitext(path.join(currentDir, img))

                LOGGER.info('-'*50)
                LOGGER.info('Renaming: ' + path.join(currentDir, img) + ' ---> ' + path.join(topDir, ZIP_DIR, str(dirCounter) + '-' + str(counter) + ext))
                counter += 1
                copy2(path.join(currentDir, img), path.join(topDir, ZIP_DIR, str(dirCounter) + '-' + str(counter) + ext))
                LOGGER.info('-'*50)
            dirCounter += 1


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

    VOLS_DIR = path.join(topDir, 'zipped_volumes')
    makeDirectory(VOLS_DIR)

    IMGS_DIR = path.join(topDir, ZIP_DIR)
    os.chdir(IMGS_DIR)

    # Organize chapters by volume
    if merge.params.volumize:
        LOGGER.info('Starting to volumize chapters.')
        # Get stes of pre-sorted volumes keys, and all the images extracted
        volumes = getVolumes(IMGS_DIR)

        # Zip images by volume
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
            with ZipFile(currentArchive, 'w') as zf:
                for img in imgs:
                    LOGGER.debug('Adding: ' + img)
                    zf.write(img)
    else:
        ARCHIVE = path.join(topDir, merge.params.archive + ARCHIVE_EXT)
        with ZipFile(ARCHIVE, 'w') as zf:
            LOGGER.info('Compressing images...')
            for root, dirs, imgs in walk('.'):
                for img in natsorted(imgs):
                    LOGGER.debug('Adding: ' + img)
                    zf.write(path.join(root, img))


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


def convertToPdf():
    """
    Converts extracted images to pdf
    """

    makeDirectory(ZIP_DIR)

    topDir = os.getcwd()

    if merge.params.volumize:
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
                LOGGER.info('-'*50)
    # TODO: Refractor to not reuse code. There must be a smarter way to do this.
    else:
        dirCounter = 0
        for dir in natsorted(os.listdir(EXTRACT_DIR)):
            counter = 0
            currentDir = path.join(topDir, EXTRACT_DIR, dir)
            # Move images to ZIP_DIR, renaming them to be continuous
            for img in natsorted(os.listdir(currentDir)):
                name, ext = path.splitext(path.join(currentDir, img))

                LOGGER.info('-'*50)
                LOGGER.info('Renaming: ' + path.join(currentDir, img) + ' ---> ' + path.join(topDir, ZIP_DIR, str(dirCounter) + '-' + str(counter) + ext))
                counter += 1
                copy2(path.join(currentDir, img), path.join(topDir, ZIP_DIR, str(dirCounter) + '-' + str(counter) + ext))
                LOGGER.info('-'*50)
            dirCounter += 1


def makeDirectory(name):
    """
    Creates directory <name>, but only if it doesn't
    exist already.
    :param name: Directory to create
    """
    if not path.isdir(name):
        os.mkdir(name)






# Script parameters
merge.add_param('path', help='path to your cbz archives', type=str)
merge.add_param('-a', '--archive', help='name of your compressed cbz file', type=str, default='CBZ_Archive')
merge.add_param('-vo', '--volumize', help='generate one archive per volume, using user provided regex', default=False, type=str)
merge.add_param('--pdf', help='output in pdf format', default=False, action="store_true")

if __name__ == "__main__":
    merge.run()
