#!/usr/bin/python

import os
import cli.app
import cli.log
import logging
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

    extractCbz(merge.params.path)
    renameImages()
    zipImages()
    print('\nAll done!')


def extractCbz(dir):
    """
    Extracts all zip (or cbz) archives found in dir, at
    the top level, to folders of the same name as the archive,
    locating them in a root folder called ".extracted"
    :param dir: Directory containing the zip files.
    """
    # Ensure that directory exists
    if not path.isdir(path.join('.', EXTRACT_DIR)):
        os.mkdir(EXTRACT_DIR)

    # Extract cbz files and move them to their own folder, inside
    # <EXTRACT_DIR>
    for file in natsorted(os.listdir('.')):

        if file == EXTRACT_DIR or file == ZIP_DIR:
            continue

        name, ext = path.splitext(file)
        LOGGER.info('-'*50)
        LOGGER.info('Creating directory for: ' + name)
        extract_path = path.join(EXTRACT_DIR, name)
        if not path.isdir(extract_path):
            LOGGER.info(extract_path + 'already exists. Using that directory for extracted files.')
            os.mkdir(extract_path)

        LOGGER.info('Extracting: ' + name + '...')
        with ZipFile(file, 'r') as zipObj:
            zipObj.extractall(extract_path)
        LOGGER.info('-'*50)


def renameImages():
    """
    Rename images extracted with extractCbz(). The naming convention is
    <folderName>-<imgNumber>.<extension>
    """

    if not path.isdir(ZIP_DIR):
        os.mkdir(ZIP_DIR)

    topDir = os.getcwd()
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


def zipImages():
    """
    TODO: Write description
    """
    ARCHIVE = path.join(os.getcwd(), merge.params.archive)
    os.chdir(ZIP_DIR)
    with ZipFile(ARCHIVE + '.cbz', 'w') as zf:
        LOGGER.info('Compressing images...')
        for root, dirs, imgs in walk('.'):
            for img in natsorted(imgs):
                LOGGER.debug('Adding: ' + img)
                zf.write(path.join(root, img))

# Script parameters
merge.add_param('path', help='path to your cbz archives', type=str)
merge.add_param('archive', help='name of your compressed cbz file', type=str)

if __name__ == "__main__":
    merge.run()
