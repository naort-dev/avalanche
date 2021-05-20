################################################################################
# Copyright (c) 2021 ContinualAI.                                              #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 20-05-2020                                                             #
# Author: Matthias De Lange                                                    #
# E-mail: contact@continualai.org                                              #
# Website: continualai.org                                                     #
################################################################################


from avalanche.benchmarks.datasets import INATURALIST2018
from avalanche.benchmarks import nc_benchmark

from torchvision import transforms

normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])

_default_train_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    normalize
])

_default_eval_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    normalize
])


def SplitInaturalist(root,
                     super_categories=None,
                     return_task_id=False,
                     download=False,
                     seed=0,
                     train_transform=_default_train_transform,
                     eval_transform=_default_eval_transform):
    """
    Creates a CL scenario using the iNaturalist2018 dataset.
    A selection of supercategories (by default 10) define the experiences.
    Note that the supercategories are highly imbalanced in the number of classes
    and the amount of data available.

    If the dataset is not present in the computer, **this method will
    automatically download** and store it if `download=True`
    (120Gtrain/val).

    Implementation is based on the CL survey
    (https://ieeexplore.ieee.org/document/9349197) but differs slightly.
    The survey uses only the original iNaturalist2018 training dataset split
    into 70/10/20 for train/val/test streams. This method instead uses the full
    iNaturalist2018 training set to make the `train_stream`, whereas the
    `test_stream` is defined by the original iNaturalist2018 validation data.

    The returned scenario will return experiences containing all patterns of a
    subset of classes, which means that each class is only seen "once".
    This is one of the most common scenarios in the Continual Learning
    literature. Common names used in literature to describe this kind of
    scenario are "Class Incremental", "New Classes", etc. By default,
    an equal amount of classes will be assigned to each experience.

    This generator doesn't force a choice on the availability of task labels,
    a choice that is left to the user (see the `return_task_id` parameter for
    more info on task labels).

    The scenario instance returned by this method will have two fields,
    `train_stream` and `test_stream`, which can be iterated to obtain
    training and test :class:`Experience`. Each Experience contains the
    `dataset` and the associated task label.

    The scenario API is quite simple and is uniform across all scenario
    generators. It is recommended to check the tutorial of the "benchmark" API,
    which contains usage examples ranging from "basic" to "advanced".

    :param root: Base path where Inaturalist data is stored.
    :param super_categories: The list of supercategories which define the
    tasks, i.e. each task consists of all classes in a super-category.
    :param download: If true and the dataset is not present in the computer,
    this method will automatically download and store it. This will take 120G
    for the train/val set.
    :param return_task_id: if True, a progressive task id is returned for every
        experience. If False, all experiences will have a task ID of 0.
    :param seed: A valid int used to initialize the random number generator.
        Can be None.
    :param train_transform: The transformation to apply to the training data,
        e.g. a random crop, a normalization or a concatenation of different
        transformations (see torchvision.transform documentation for a
        comprehensive list of possible transformations).
        If no transformation is passed, the default train transformation
        will be used.
    :param eval_transform: The transformation to apply to the test data,
        e.g. a random crop, a normalization or a concatenation of different
        transformations (see torchvision.transform documentation for a
        comprehensive list of possible transformations).
        If no transformation is passed, the default test transformation
        will be used.

    :returns: A properly initialized :class:`NCScenario` instance.
    """

    # Categories with > 100 datapoints
    if super_categories is None:
        super_categories = [
            'Amphibia', 'Animalia', 'Arachnida', 'Aves', 'Fungi',
            'Insecta', 'Mammalia', 'Mollusca', 'Plantae', 'Reptilia']

    train_set, test_set = _get_inaturalist_dataset(
        root, super_categories, download)

    per_exp_classes = _get_per_exp_classes(super_categories, train_set)

    if return_task_id:
        return nc_benchmark(
            train_dataset=train_set,
            test_dataset=test_set,
            n_experiences=len(super_categories),
            task_labels=True,
            per_exp_classes=per_exp_classes,
            seed=seed,
            class_ids_from_zero_in_each_exp=True,
            train_transform=train_transform,
            eval_transform=eval_transform)
    else:
        return nc_benchmark(
            train_dataset=train_set,
            test_dataset=test_set,
            n_experiences=len(super_categories),
            task_labels=False,
            per_exp_classes=per_exp_classes,
            seed=seed,
            train_transform=train_transform,
            eval_transform=eval_transform)


def _get_inaturalist_dataset(root, super_categories, download):
    train_set = INATURALIST2018(root, split="train", supcats=super_categories,
                                download=download)
    test_set = INATURALIST2018(root, split="val", supcats=super_categories,
                               download=download)

    return train_set, test_set


def _get_per_exp_classes(super_categories, train_set):
    """Map list of super_categories to index-incremental dictionary."""
    ret = {}
    for idx, supcat in enumerate(super_categories):
        ret[idx] = train_set.cats_per_supcat[supcat]
    return ret


__all__ = [
    'SplitInaturalist'
]

if __name__ == "__main__":
    scenario = SplitInaturalist(
        "/usr/data/delangem/inaturalist2018")  # TODO remove
    for exp in scenario.train_stream:
        print("experience: ", exp.current_experience)
        print("classes number: ", len(exp.classes_in_this_experience))
        print("classes: ", exp.classes_in_this_experience)
