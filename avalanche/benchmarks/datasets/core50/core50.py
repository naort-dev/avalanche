################################################################################
# Copyright (c) 2021 ContinualAI.                                              #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 10-10-2020                                                             #
# Author: Vincenzo Lomonaco                                                    #
# E-mail: contact@continualai.org                                              #
# Website: www.continualai.org                                                 #
################################################################################

""" CORe50 Pytorch Dataset """

import os
import logging
from torch.utils.data.dataset import Dataset
from torchvision.transforms import ToTensor
from PIL import Image
import pickle as pkl
from os.path import expanduser
from .core50_data import CORE50_DATA


def pil_loader(path):
    """ Load an Image with PIL """
    # open path as file to avoid ResourceWarning
    # (https://github.com/python-pillow/Pillow/issues/835)
    with open(path, 'rb') as f:
        img = Image.open(f)
        return img.convert('RGB')


class CORe50(Dataset):
    """ CORe50 Pytorch Dataset """

    def __init__(self, root=expanduser("~")+"/.avalanche/data/core50/",
                 train=True, transform=ToTensor(), target_transform=None,
                 loader=pil_loader, download=True, mini=False,
                 object_level=True):
        """

        :param root: root for the datasets data.
        :param train: train or test split.
        :param transform: eventual transformations to be applied.
        :param target_transform: eventual transformation to be applied to the
            targets.
        :param loader: data loader method from disk.
        :param download: boolean to automatically download data. Default to
            True.
        :param mini: boolean to use the 32x32 version instead of the 128x128.
            Default to False.
        :param object_level: if the classification is objects based or
            category based: 50 or 10 way classification problem. Default to True
            (50-way object classification problem)
        """

        self.train = train  # training set or test set
        self.transform = transform
        self.target_transform = target_transform
        self.root = root
        self.loader = loader
        self.object_level = object_level
        self.mini = mini
        self.log = logging.getLogger("avalanche")

        # any scenario and run is good here since we want just to load the
        # train images and targets with no particular order
        scen = 'ni'
        run = 0
        nbatch = 8

        if download:
            self.core_data = CORE50_DATA(data_folder=root, mini=mini)

        self.log.info("Loading paths...")
        with open(os.path.join(root, 'paths.pkl'), 'rb') as f:
            self.train_test_paths = pkl.load(f)

        self.log.info("Loading labels...")
        with open(os.path.join(root, 'labels.pkl'), 'rb') as f:
            self.all_targets = pkl.load(f)
            self.train_test_targets = []
            for i in range(nbatch + 1):
                self.train_test_targets += self.all_targets[scen][run][i]

        self.log.info("Loading LUP...")
        with open(os.path.join(root, 'LUP.pkl'), 'rb') as f:
            self.LUP = pkl.load(f)

        self.log.info("Loading labels names...")
        with open(os.path.join(root, 'labels2names.pkl'), 'rb') as f:
            self.labels2names = pkl.load(f)

        self.idx_list = []
        if train:
            for i in range(nbatch + 1):
                self.idx_list += self.LUP[scen][run][i]
        else:
            self.idx_list = self.LUP[scen][run][-1]

        self.paths = []
        self.targets = []

        for idx in self.idx_list:
            self.paths.append(self.train_test_paths[idx])
            div = 1
            if not self.object_level:
                div = 5
            self.targets.append(self.train_test_targets[idx] // div)

    def __getitem__(self, index):
        """
        Args:
            index (int): Index

        Returns:
            tuple: (sample, target) where target is class_index of the target
                class.
        """

        if self.mini:
            bp = "core50_32x32"
        else:
            bp = "core50_128x128"

        target = self.targets[index]
        img = self.loader(
            os.path.join(
                self.root, bp, self.paths[index]
            )
        )
        if self.transform is not None:
            img = self.transform(img)
        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target

    def __len__(self):
        return len(self.targets)


if __name__ == "__main__":

    # this litte example script can be used to visualize the first image
    # leaded from the dataset.
    from torch.utils.data.dataloader import DataLoader
    import matplotlib.pyplot as plt
    from torchvision import transforms
    import torch

    train_data = CORe50()
    test_data = CORe50(train=False)
    print("train size: ", len(train_data))
    print("Test size: ", len(test_data))
    print(train_data.labels2names)
    dataloader = DataLoader(train_data, batch_size=1)

    for batch_data in dataloader:
        x, y = batch_data
        plt.imshow(
            transforms.ToPILImage()(torch.squeeze(x))
        )
        plt.show()
        print(x.size())
        print(len(y))
        break


__all__ = [
    'CORe50'
]
