# The dataset code has been adapted from:
# https://github.com/yaoyao-liu/mini-imagenet-tools
# which has been distributed under the following license:
################################################################################
# MIT License
#
# Copyright (c) 2019 Yaoyao Liu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
################################################################################

# CSVs are taken from the aforementioned repository and were created by
# Ravi and Larochelle. CSVs are distributed under the following license:
################################################################################
# MIT License
#
# Copyright (c) 2016 Twitter, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
################################################################################

# For the Avalanche data loader adaptation:
################################################################################
# Copyright (c) 2021 ContinualAI.                                              #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 15-02-2020                                                             #
# Author: Lorenzo Pellegrini                                                   #
# E-mail: contact@continualai.org                                              #
# Website: www.continualai.org                                                 #
################################################################################

import csv
import glob
from pathlib import Path
from typing import Union, List, Tuple, Dict

from torchvision.datasets.folder import default_loader
from typing_extensions import Literal

import PIL
import numpy as np
from PIL import Image
from torch.utils.data.dataset import Dataset
from torchvision.transforms import Resize

from avalanche.benchmarks.datasets.mini_imagenet.mini_imagenet_data import (
    MINI_IMAGENET_WNIDS,
    MINI_IMAGENET_WNID_TO_IDX,
    MINI_IMAGENET_CLASSES,
    MINI_IMAGENET_CLASS_TO_IDX,
)


class MiniImageNetDataset(Dataset):
    """
    The MiniImageNet dataset.

    This implementation is based on the one from
    https://github.com/yaoyao-liu/mini-imagenet-tools. Differently from that,
    this class doesn't rely on a pre-generated mini imagenet folder. Instead,
    this will use the original ImageNet folder by resizing images on-the-fly.

    The list of included files are the ones defined in the CSVs taken from the
    aforementioned repository. Those CSVs are generated by Ravi and Larochelle.
    See the linked repository for more details.

    Exactly as happens with the torchvision :class:`ImageNet` class, textual
    class labels (wnids) such as "n02119789", "n02102040", etc. are mapped to
    numerical labels based on their ascending order.

    All the fields found in the torchvision implementation of the ImageNet
    dataset (`wnids`, `wnid_to_idx`, `classes`, `class_to_idx`) are available.
    """

    def __init__(
        self,
        imagenet_path: Union[str, Path],
        split: Literal["all", "train", "val", "test"] = "all",
        resize_to: Union[int, Tuple[int, int]] = 84,
        loader=default_loader,
    ):
        """
        Creates an instance of the Mini ImageNet dataset.

        This dataset allows to obtain the whole dataset or even only specific
        splits. Beware that, when using a split different that "all", the
        returned dataset will contain patterns of a subset of the 100 classes.
        This happens because MiniImagenet was created with the idea of training,
        validating and testing on a disjoint set of classes.

        This implementation uses the filelists provided by
        https://github.com/yaoyao-liu/mini-imagenet-tools, which are the ones
        generated by Ravi and Larochelle (see the linked repo for more details).

        :param imagenet_path: The path to the imagenet folder. This has to be
            the path to the full imagenet 2012 folder (plain, not resized).
            Only the "train" folder will be used. Because of this, passing the
            path to the imagenet 2012 "train" folder is also allowed.
        :param split: The split to obtain. Defaults to "all". Valid values are
            "all", "train", "val" and "test".
        :param resize_to: The size of the output images. Can be an `int` value
            or a tuple of two ints. When passing a single `int` value, images
            will be resized by forcing as 1:1 aspect ratio. Defaults to 84,
            which means that images will have size 84x84.
        """
        self.imagenet_path = MiniImageNetDataset.get_train_path(imagenet_path)
        """
        The path to the "train" folder of full imagenet 2012 directory.
        """

        self.split: Literal["all", "train", "val", "test"] = split
        """
        The required split.
        """

        if isinstance(resize_to, int):
            resize_to = (resize_to, resize_to)

        self.resize_to: Tuple[int, int] = resize_to
        """
        The size of the output images, as a two ints tuple.
        """

        # TODO: the original loader from yaoyao-liu uses cv2.INTER_AREA
        self._transform = Resize(self.resize_to, interpolation=PIL.Image.BILINEAR)

        # The following fields are filled by self.prepare_dataset()
        self.image_paths: List[str] = []
        """
        The paths to images.
        """

        self.targets: List[int] = []
        """
        The class labels for the patterns. Aligned with the image_paths field.
        """

        self.wnids: List[str] = []
        """
        The list of wnids (the textual class labels, such as "n02119789").
        """

        self.wnid_to_idx: Dict[str, int] = dict()
        """
        A dictionary mapping wnids to numerical labels in range [0, 100).
        """

        self.classes: List[Tuple[str, ...]] = []
        """
        A list mapping numerical labels (the element index) to a tuple of human
        readable categories. For instance:
        ('great grey owl', 'great gray owl', 'Strix nebulosa').
        """

        self.class_to_idx: Dict[str, int] = dict()
        """
        A dictionary mapping each string of the tuples found in the classes 
        field to their numerical label. That is, this dictionary contains the 
        inverse mapping of classes field.
        """

        self.loader = loader

        if not self.imagenet_path.exists():
            raise ValueError("The provided directory does not exist.")

        if self.split not in ["all", "train", "val", "test"]:
            raise ValueError(
                'Invalid split. Valid values are: "train", "val", ' '"test"'
            )

        self.prepare_dataset()

        super().__init__()

    @staticmethod
    def get_train_path(root_path: Union[str, Path]):
        root_path = Path(root_path)
        if (root_path / "train").exists():
            return root_path / "train"
        return root_path

    def prepare_dataset(self):
        # Read the CSV containing the file list for this split
        images: Dict[str, List[str]] = dict()

        csv_dir = Path(__file__).resolve().parent / "csv_files"
        if self.split == "all":
            considered_csvs = ["train.csv", "val.csv", "test.csv"]
        else:
            considered_csvs = [self.split + ".csv"]

        for csv_name in considered_csvs:
            csv_path = str(csv_dir / csv_name)

            with open(csv_path) as csvfile:
                csv_reader = csv.reader(csvfile, delimiter=",")
                next(csv_reader, None)  # Skip header

                for row in csv_reader:
                    if row[1] in images.keys():
                        images[row[1]].append(row[0])
                    else:
                        images[row[1]] = [row[0]]

        # Fill fields like wnids, wnid_to_idx, etc.
        # Those fields have the same meaning of the ones found in the
        # torchvision implementation of the ImageNet dataset. Of course some
        # work had to be done to keep this fields aligned for mini imagenet,
        # which only contains 100 classes of the original 1000.
        #
        # wnids are 'n01440764', 'n01443537', 'n01484850', etc.
        #
        # self.wnid_to_idx is a dict mapping wnids to numerical labels
        #
        # self.classes is a list mapping numerical labels (the element
        # index) to a tuple of human readable categories. For instance:
        # ('great grey owl', 'great gray owl', 'Strix nebulosa').
        #
        # self.class_to_idx is a dict mapping each string of the
        # aforementioned tuples to its numerical label. That is, it contains
        # the inverse mapping of self.classes.
        self.wnids = MINI_IMAGENET_WNIDS
        self.wnid_to_idx = MINI_IMAGENET_WNID_TO_IDX
        self.classes = MINI_IMAGENET_CLASSES
        self.class_to_idx = MINI_IMAGENET_CLASS_TO_IDX

        for cls in images.keys():
            cls_numerical_label = self.wnid_to_idx[cls]
            lst_files = []
            for file in glob.glob(str(self.imagenet_path / cls / ("*" + cls + "*"))):
                lst_files.append(file)

            lst_index = [int(i[i.rfind("_") + 1 : i.rfind(".")]) for i in lst_files]
            index_sorted = sorted(range(len(lst_index)), key=lst_index.__getitem__)

            index_selected = [
                int(i[i.index(".") - 4 : i.index(".")]) for i in images[cls]
            ]
            selected_images = np.array(index_sorted)[np.array(index_selected) - 1]
            for i in np.arange(len(selected_images)):
                self.image_paths.append(lst_files[selected_images[i]])
                self.targets.append(cls_numerical_label)

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, item):
        img = self.loader(self.image_paths[item])
        img = self._transform(img)
        return img, self.targets[item]


__all__ = ["MiniImageNetDataset"]

if __name__ == "__main__":
    import matplotlib.pyplot as plt

    print("Creating training dataset")
    train_dataset = MiniImageNetDataset("/ssd2/datasets/imagenet", split="train")
    print("Creating validation dataset")
    val_dataset = MiniImageNetDataset("/ssd2/datasets/imagenet", split="val")
    print("Creating test dataset")
    test_dataset = MiniImageNetDataset("/ssd2/datasets/imagenet", split="test")

    print("Training patterns:", len(train_dataset))
    print("Validation patterns:", len(val_dataset))
    print("Test patterns:", len(test_dataset))

    for img_idx, (img, label) in enumerate(train_dataset):
        plt.title(
            "Class {}, {}\n{}".format(
                label,
                train_dataset.classes[label],
                train_dataset.image_paths[0],
            )
        )
        plt.imshow(img)
        plt.show()
        print(img)
        print(label)
        class_to_idx = train_dataset.class_to_idx[train_dataset.classes[label][0]]
        assert class_to_idx == label
        if img_idx == 2:
            break

    for img_idx, (img, label) in enumerate(val_dataset):
        plt.title(
            "Class {}, {}\n{}".format(
                label, val_dataset.classes[label], val_dataset.image_paths[0]
            )
        )
        plt.imshow(img)
        plt.show()
        print(img)
        print(label)
        class_to_idx = val_dataset.class_to_idx[train_dataset.classes[label][0]]
        assert class_to_idx == label
        if img_idx == 2:
            break

    for img_idx, (img, label) in enumerate(test_dataset):
        plt.title(
            "Class {}, {}\n{}".format(
                label, test_dataset.classes[label], test_dataset.image_paths[0]
            )
        )
        plt.imshow(img)
        plt.show()
        print(img)
        print(label)
        class_to_idx = test_dataset.class_to_idx[train_dataset.classes[label][0]]
        assert class_to_idx == label
        if img_idx == 2:
            break
