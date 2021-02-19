################################################################################
# Copyright (c) 2020 ContinualAI                                               #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 19-01-2021                                                             #
# Author(s): Lorenzo Pellegrini                                                #
# E-mail: contact@continualai.org                                              #
# Website: www.continualai.org                                                 #
################################################################################

from typing import SupportsFloat

from avalanche.evaluation import Metric


class Mean(Metric[float]):
    """
    The mean metric.

    This utility metric is a general purpose metric that can be used to keep
    track of the mean of a sequence of values.
    """
    def __init__(self):
        """
        Creates an instance of the mean metric.

        This metric in its initial state will return a mean value of 0.
        The metric can be updated by using the `update` method while the mean
        can be retrieved using the `result` method.
        """
        super().__init__()
        self.summed: float = 0.0
        self.weight: float = 0.0

    def update(self, value: SupportsFloat, weight: SupportsFloat = 1.0) -> None:
        """
        Update the running mean given the value.

        The value can be weighted with a custom value, defined by the `weight`
        parameter.

        :param value: The value to be used to update the mean.
        :param weight: The weight of the value. Defaults to 1.
        :return: None.
        """
        value = float(value)
        weight = float(weight)
        self.summed += value * weight
        self.weight += weight

    def result(self) -> float:
        """
        Retrieves the mean.

        Calling this method will not change the internal state of the metric.

        :return: The mean, as a float.
        """
        if self.weight == 0.0:
            return 0.0
        return self.summed / self.weight

    def reset(self) -> None:
        """
        Resets the metric.

        :return: None.
        """
        self.summed = 0.0
        self.weight = 0.0


__all__ = ['Mean']
