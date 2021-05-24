################################################################################
# Copyright (c) 2021 ContinualAI.                                              #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 12-04-2021                                                             #
# Author: Lorenzo Pellegrini, Vincenzo Lomonaco                                #
# E-mail: contact@continualai.org                                              #
# Website: continualai.org                                                     #
################################################################################

"""
CUB200 Pytorch Dataset: Caltech-UCSD Birds-200-2011 (CUB-200-2011) is an
extended version of the CUB-200 dataset, with roughly double the number of
images per class and new part location annotations. For detailed information
about the dataset, please check the official website:
http://www.vision.caltech.edu/visipedia/CUB-200-2011.html.
"""

import csv
import gdown
import os
from collections import OrderedDict
from os.path import expanduser
from torchvision.datasets.folder import default_loader
from torchvision.datasets.utils import extract_archive

from avalanche.benchmarks.utils import PathsDataset


class CUB200(PathsDataset):
    """ Basic CUB200 PathsDataset to be used as a standard PyTorch Dataset.
        A classic continual learning benchmark built on top of this dataset
        can be found in 'benchmarks.classic', while for more custom benchmark
        design please use the 'benchmarks.generators'."""

    images_folder = 'CUB_200_2011/images'
    official_url = 'http://www.vision.caltech.edu/visipedia-data/CUB-200-2011/'\
                   'CUB_200_2011.tgz'
    gdrive_url = "https://drive.google.com/u/0/uc?id=" \
                 "1hbzc_P1FuxMkcabkgn9ZKinBwW683j45"
    filename = 'CUB_200_2011.tgz'
    tgz_md5 = '97eceeb196236b17998738112f37df78'

    def __init__(
            self, root=expanduser("~") + "/.avalanche/data/CUB_200_2011/",
            train=True, transform=None, target_transform=None,
            loader=default_loader, download=True):
        """

        :param root: root dir where the dataset can be found or downloaded.
            Default to '~/.avalanche/data/CUB_200_2011'.
        :param train: train or test subset of the original dataset. Default
            to True.
        :param transform: eventual input data transformations to apply.
            Default to None.
        :param target_transform: eventual target data transformations to apply.
            Default to None.
        :param loader: method to load the data from disk. Default to
            torchvision default_loader.
        :param download: default set to True. If the data is already
            downloaded it will skip the download.
        """

        self.root = os.path.expanduser(root)
        self.train = train

        # we create the dir if it does not exists
        if not os.path.exists(self.root):
            os.makedirs(self.root)

        if not self._check_integrity():
            if download:
                self._download()
            else:
                raise RuntimeError('Dataset not found or corrupted. ')

        super().__init__(
            os.path.join(self.root, CUB200.images_folder), self._images,
            transform=transform, target_transform=target_transform,
            loader=loader)

    def _load_metadata(self):
        """ Main method to load the CUB200 metadata """

        cub_dir = os.path.join(self.root, 'CUB_200_2011')
        self._images = OrderedDict()

        with open(os.path.join(cub_dir, 'train_test_split.txt')) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=' ')
            for row in csv_reader:
                img_id = int(row[0])
                is_train_instance = int(row[1]) == 1
                if is_train_instance == self.train:
                    self._images[img_id] = []

        with open(os.path.join(cub_dir, 'images.txt')) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=' ')
            for row in csv_reader:
                img_id = int(row[0])
                if img_id in self._images:
                    self._images[img_id].append(row[1])

        with open(os.path.join(cub_dir, 'image_class_labels.txt')) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=' ')
            for row in csv_reader:
                img_id = int(row[0])
                if img_id in self._images:
                    # CUB starts counting classes from 1 ...
                    self._images[img_id].append(int(row[1]) - 1)

        with open(os.path.join(cub_dir, 'bounding_boxes.txt')) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=' ')
            for row in csv_reader:
                img_id = int(row[0])
                if img_id in self._images:
                    box_cub = [int(float(x)) for x in row[1:]]
                    box_avl = [box_cub[1], box_cub[0], box_cub[3], box_cub[2]]
                    # PathsDataset accepts (top, left, height, width)
                    self._images[img_id].append(box_avl)

        images_tuples = []
        for _, img_tuple in self._images.items():
            images_tuples.append(tuple(img_tuple))
        self._images = images_tuples

    def _check_integrity(self):
        """ Checks if the data is already available and intact """

        try:
            self._load_metadata()
        except Exception as _:
            return False

        for row in self._images:
            filepath = os.path.join(self.root, CUB200.images_folder, row[0])
            if not os.path.isfile(filepath):
                print('[CUB200] Error checking integrity of:', filepath)
                return False
        return True

    def _download(self):
        if self._check_integrity():
            print('Files already downloaded and verified')
            return

        try:
            filepath = os.path.join(self.root, self.filename)
            gdown.download(self.gdrive_url, filepath, quiet=False)
            gdown.cached_download(
                self.gdrive_url, filepath, md5=self.tgz_md5
            )
        except Exception as e:
            print('[CUB200] Direct download may no longer be supported!')
            raise e

        extract_archive(filepath, to_path=self.root)


if __name__ == "__main__":

    """ Simple test that will start if you run this script directly """

    import matplotlib.pyplot as plt
    dataset = CUB200(train=False, download=True)
    print("test data len:", len(dataset))
    img, _ = dataset[14]
    plt.imshow(img)
    plt.show()

    dataset = CUB200(train=True)
    print("train data len:", len(dataset))
    img, _ = dataset[700]
    plt.imshow(img)
    plt.show()


__all__ = [
    'CUB200'
]
