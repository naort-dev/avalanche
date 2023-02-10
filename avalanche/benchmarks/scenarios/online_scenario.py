################################################################################
# Copyright (c) 2022 ContinualAI.                                              #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 11-04-2022                                                             #
# Author(s): Antonio Carta                                                     #
# E-mail: contact@continualai.org                                              #
# Website: avalanche.continualai.org                                           #
################################################################################
from copy import copy
from typing import Callable, Iterable, List, Union

import torch

from avalanche.benchmarks.scenarios.generic_scenario import (
    CLExperience,
    EagerCLStream,
    CLStream,
    ExperienceAttribute,
    CLScenario,
)
from avalanche.benchmarks.utils import classification_subset


class OnlineCLExperience(CLExperience):
    """Online CL (OCL) Experience.

    OCL experiences are created by splitting a larger experience. Therefore,
    they keep track of the original experience for logging purposes.
    """

    def __init__(
        self,
        current_experience: int = None,
        origin_stream=None,
        origin_experience=None,
        subexp_size: int = 1,
        is_first_subexp: bool = False,
        is_last_subexp: bool = False,
        sub_stream_length: int = None,
        access_task_boundaries: bool = False,
    ):
        """Init.

        :param current_experience: experience identifier.
        :param origin_stream: origin stream.
        :param origin_experience: origin experience used to create self.
        :param is_first_subexp: whether self is the first in the sub-experiences
            stream.
        :param sub_stream_length: the sub-stream length.
        """
        super().__init__(current_experience, origin_stream)
        self.access_task_boundaries = access_task_boundaries

        self.origin_experience = ExperienceAttribute(
            origin_experience, use_in_train=access_task_boundaries
        )
        self.subexp_size = ExperienceAttribute(
            subexp_size, use_in_train=access_task_boundaries
        )
        self.is_first_subexp = ExperienceAttribute(
            is_first_subexp, use_in_train=access_task_boundaries
        )
        self.is_last_subexp = ExperienceAttribute(
            is_last_subexp, use_in_train=access_task_boundaries
        )
        self.sub_stream_length = ExperienceAttribute(
            sub_stream_length, use_in_train=access_task_boundaries
        )


def fixed_size_experience_split(
    experience: CLExperience,
    experience_size: int,
    shuffle: bool = True,
    drop_last: bool = False,
    access_task_boundaries: bool = False,
):
    """Returns a lazy stream generated by splitting an experience into smaller
    ones.

    Splits the experience in smaller experiences of size `experience_size`.

    :param experience: The experience to split.
    :param experience_size: The experience size (number of instances).
    :param shuffle: If True, instances will be shuffled before splitting.
    :param drop_last: If True, the last mini-experience will be dropped if
        not of size `experience_size`
    :return: The list of datasets that will be used to create the
        mini-experiences.
    """

    def gen():
        exp_dataset = experience.dataset
        exp_indices = list(range(len(exp_dataset)))
        exp_targets = torch.LongTensor(list(exp_dataset.targets))

        if shuffle:
            exp_indices = torch.as_tensor(exp_indices)[
                torch.randperm(len(exp_indices))
            ].tolist()
        sub_stream_length = len(exp_indices) // experience_size
        if not drop_last and len(exp_indices) % experience_size > 0:
            sub_stream_length += 1

        init_idx = 0
        is_first = True
        is_last = False
        while init_idx < len(exp_indices):
            final_idx = init_idx + experience_size  # Exclusive
            if final_idx > len(exp_indices):
                if drop_last:
                    break

                final_idx = len(exp_indices)
                is_last = True

            exp = OnlineCLExperience(
                origin_experience=experience,
                subexp_size=experience_size,
                is_first_subexp=is_first,
                is_last_subexp=is_last,
                sub_stream_length=sub_stream_length,
                access_task_boundaries=access_task_boundaries,
            )
            exp.dataset = exp_dataset.subset(exp_indices[init_idx:final_idx])

            # Add sub-experience attributes
            exp.classes_in_this_experience = list(
                exp_targets[exp_indices[init_idx:final_idx]].unique().numpy())
            exp.task_labels = experience.task_labels

            is_first = False
            yield exp
            init_idx = final_idx

    return gen()


def split_online_stream(
    original_stream: EagerCLStream,
    experience_size: int,
    shuffle: bool = False,
    drop_last: bool = False,
    experience_split_strategy: Callable[
        [CLExperience], Iterable[CLExperience]
    ] = None,
    access_task_boundaries: bool = False,
):
    """Split a stream of large batches to create an online stream of small
    mini-batches.

    The resulting stream can be used for Online Continual Learning (OCL)
    scenarios (or data-incremental, or other online-based settings).

    For efficiency reasons, the resulting stream is an iterator, generating
    experience on-demand.

    :param original_stream: The stream with the original data.
    :param experience_size: The size of the experience, as an int. Ignored
        if `custom_split_strategy` is used.
    :param shuffle: If True, experiences will be split by first shuffling
        instances in each experience. This will use the default PyTorch
        random number generator at its current state. Defaults to False.
        Ignored if `experience_split_strategy` is used.
    :param drop_last: If True, if the last experience doesn't contain
        `experience_size` instances, then the last experience will be dropped.
        Defaults to False. Ignored if `experience_split_strategy` is used.
    :param experience_split_strategy: A function that implements a custom
        splitting strategy. The function must accept an experience and return an
        experience's iterator. Defaults to None, which means
        that the standard splitting strategy will be used (which creates
        experiences of size `experience_size`).
        A good starting to understand the mechanism is to look at the
        implementation of the standard splitting function
        :func:`fixed_size_experience_split_strategy`.
    :return: A lazy online stream with experiences of size `experience_size`.
    """
    if experience_split_strategy is None:

        def split_foo(exp: CLExperience, size: int):
            return fixed_size_experience_split(
                exp,
                size,
                shuffle,
                drop_last,
                access_task_boundaries=access_task_boundaries,
            )

    def exps_iter():
        for exp in original_stream:
            for sub_exp in split_foo(exp, experience_size):
                yield sub_exp

    stream_name = (
        original_stream.name if hasattr(original_stream, "name") else "train"
    )
    return CLStream(
        name=stream_name, exps_iter=exps_iter(), set_stream_info=True
    )


class OnlineCLScenario(CLScenario):
    def __init__(
        self,
        original_streams: List[EagerCLStream],
        experiences: Union[CLExperience, Iterable[CLExperience]] = None,
        experience_size: int = 10,
        stream_split_strategy="fixed_size_split",
        access_task_boundaries: bool = False,
    ):
        """Creates an online scenario from an existing CL scenario

        :param original_streams: The streams from the original CL scenario.
        :param experiences: If None, the online stream will be created
            from the `train_stream` of the original CL scenario, otherwise it
            will create an online stream from the given sequence of experiences.
        :param experience_size: The size of each online experiences, as an int.
            Ignored if `custom_split_strategy` is used.
        :param experience_split_strategy: A function that implements a custom
            splitting strategy. The function must accept an experience and
            return an experience's iterator. Defaults to None, which means
            that the standard splitting strategy will be used (which creates
            experiences of size `experience_size`).
            A good starting to understand the mechanism is to look at the
            implementation of the standard splitting function
            :func:`fixed_size_experience_split_strategy`.
        : param access_task_boundaries: If True the attributes related to task
            boundaries such as `is_first_subexp` and `is_last_subexp` become
            accessible during training. For models with dynamic modules, this
            parameter must be set to True.
        """
        if stream_split_strategy == "fixed_size_split":

            def split_foo(s):
                return split_online_stream(
                    s,
                    experience_size,
                    access_task_boundaries=access_task_boundaries,
                )

        else:
            raise ValueError("Unknown experience split strategy")

        streams_dict = {s.name: s for s in original_streams}
        if "train" not in streams_dict:
            raise ValueError("Missing train stream for `original_streams`.")
        if experiences is None:
            online_train_stream = split_foo(streams_dict["train"])
        else:
            if not isinstance(experiences, Iterable):
                experiences = [experiences]
            online_train_stream = split_foo(experiences)

        streams = [online_train_stream]
        for s in original_streams:
            s = copy(s)
            name_before = s.name

            # Set attributes of the new stream
            s.name = "original_" + s.name
            s.benchmark.stream_definitions[
                s.name
            ] = s.benchmark.stream_definitions[name_before]
            setattr(
                s.benchmark,
                f"{s.name}_stream",
                getattr(s.benchmark, f"{name_before}_stream"),
            )

            streams.append(s)

        super().__init__(streams)
