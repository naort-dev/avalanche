################################################################################
# Copyright (c) 2020 ContinualAI Research                                      #
# Copyrights licensed under the CC BY 4.0 License.                             #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 12-05-2020                                                             #
# Author(s): Lorenzo Pellegrini                                                #
# E-mail: contact@continualai.org                                              #
# Website: clair.continualai.org                                               #
################################################################################

from enum import Enum
from typing import List, TypeVar, Tuple

from avalanche.training.utils.transform_dataset import IDatasetWithTargets, \
    DatasetWithTargets


class DatasetPart(Enum):
    """An enumeration defining the different dataset parts"""
    CURRENT = 1  # Classes in this batch only
    CUMULATIVE = 2  # Encountered classes (including classes in this batch)
    OLD = 3  # Encountered classes (excluding classes in this batch)
    FUTURE = 4  # Future classes
    COMPLETE = 5  # All classes (encountered + not seen yet)


class DatasetType(Enum):
    """An enumeration defining the different dataset types"""
    TRAIN = 1  # Training set
    VALIDATION = 2  # Validation (or test) set


T_train_set_w_targets = TypeVar('T_train_set_w_targets',
                                bound=IDatasetWithTargets)
T_test_set_w_targets = TypeVar('T_test_set_w_targets',
                               bound=IDatasetWithTargets)

MTSingleSet = Tuple[DatasetWithTargets, int]
MTMultipleSet = List[MTSingleSet]

__all__ = ['T_train_set_w_targets', 'T_test_set_w_targets',
           'DatasetPart', 'DatasetType', 'MTSingleSet', 'MTMultipleSet']
