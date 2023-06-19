import copy
from typing import TYPE_CHECKING, Optional
import numpy as np

import torch
from torch.optim import SGD
from torch.utils.data.dataloader import DataLoader
from torchvision.models.feature_extraction import (
    get_graph_node_names,
    create_feature_extractor
    )

from avalanche.training.plugins.strategy_plugin import SupervisedPlugin
from avalanche.training.storage_policy import ReservoirSamplingBuffer

if TYPE_CHECKING:
    from avalanche.training.templates import SupervisedTemplate


class RARPlugin(SupervisedPlugin):
    """
    Retrospective Adversarial Replay for Continual Learning
    https://openreview.net/forum?id=XEoih0EwCwL
    Continual learning is an emerging research challenge in machine learning 
    that addresses the problem where models quickly fit the most recently 
    trained-on data and are prone to catastrophic forgetting due to 
    distribution shifts --- it does this by maintaining a small historical 
    replay buffer in replay-based methods. 
    To avoid these problems, this paper proposes a method, 
    ``Retrospective Adversarial Replay (RAR)'', that synthesizes adversarial 
    samples near the forgetting boundary. RAR perturbs a buffered sample 
    towards its nearest neighbor drawn from the current task in a latent 
    representation space. By replaying such samples, we are able to refine the 
    boundary between previous and current tasks, hence combating forgetting and 
    reducing bias towards the current task. To mitigate the severity of a small 
    replay buffer, we develop a novel MixUp-based strategy to increase replay 
    variation by replaying mixed augmentations. 
    Combined with RAR, this achieves a holistic framework that helps to 
    alleviate catastrophic forgetting. We show that this excels on 
    broadly-used benchmarks and outperforms other continual learning baselines 
    especially when only a small buffer is used. We conduct a thorough 
    ablation study over each key component as well as a hyperparameter 
    sensitivity analysis to demonstrate the effectiveness and robustness of RAR.

    """

    def __init__(
        self,
        batch_size_mem: int,
        mem_size: int = 200,
        opt_lr: float = 0.1,
        name_ext_layer: str = None,
        use_adversarial_replay: bool = True,
        beta_coef: float = 0.4,
        decay_factor_fgsm: float = 1.0,
        epsilon_fgsm: float = 0.0314,
        iter_fgsm: int = 2,
        storage_policy: Optional["ReservoirSamplingBuffer"] = None,
    ):
        """
        batch_size_mem: int    : Size of the batch sampled from
                                 the bigger buffer
        mem_size: int          : Fixed memory size
        opt_lr : float         : Learning rate of the internal optimizer
        name_ext_layer: str    : Name of the layer to extract features
        use_adversarial_replay : Boolean to use or not RAR
        beta_coef: float       : coef between RAR and Buffer
        decay_factor_fgsm:     : Decay factor of FGSM
        epsilon_fgsm:          : Epsilon for FGSM
        iter_fgsm:             : Number of iterations of FGSM
        storage_policy:        : Storage Policy used for the buffer                      
        """
        super().__init__()
        self.mem_size = mem_size
        self.batch_size_mem = batch_size_mem
        self.opt_lr = opt_lr
        self.name_ext_layer = name_ext_layer

        self.use_adversarial_replay = use_adversarial_replay

        self.beta_coef = beta_coef
        # For Split-CIFAR10: 0.5, 0.1, 0.075 - mem size 200, 500 , 1000
        # Split-CIFAR100 and Split-miniImageNet: 0.4

        # FGSM
        self.decay_factor_fgsm = decay_factor_fgsm
        self.epsilon_fgsm = epsilon_fgsm
        self.iter_fgsm = iter_fgsm

        self.replay_loader = None

        if not self.use_adversarial_replay:
            self.beta_coef = 0

        if storage_policy is not None:  # Use other storage policy
            self.storage_policy = storage_policy
            assert storage_policy.max_size == self.mem_size
        else:  # Default
            self.storage_policy = ReservoirSamplingBuffer(
                max_size=self.mem_size
            )

    def before_training_exp(
        self,
        strategy: "SupervisedTemplate",
        shuffle: bool = True,
        **kwargs
    ):
        """
        Dataloader to build batches containing examples from both memories and
        the training dataset
        """
        if len(self.storage_policy.buffer) == 0:
            # first experience. We don't use the buffer
            return

        batch_size_mem = self.batch_size_mem
        if batch_size_mem is None:
            batch_size_mem = strategy.train_mb_size

        self.storage_policy.buffer

        self.replay_loader = DataLoader(
            self.storage_policy.buffer,
            batch_size=self.batch_size_mem,
            shuffle=shuffle,
        )

    def before_backward(self, strategy: "SupervisedTemplate", **kwargs):
        """
        Before the backward function in the training process. We need to update 
        the loss function.

        First we add the loss of the buffer. Then if we are using RAR, we 
        obtained the features to find the closest element of a different class.
        We apply FGSM to those selected elements and then find the loss 
        of the attacked samples. 
        """

        if len(self.storage_policy.buffer) == 0:
            # first experience. We don't use the buffer
            return

        batch_buff = self.get_buffer_batch()
        mb_x_buff = batch_buff[0].to(strategy.device)
        mb_y_buff = batch_buff[1].to(strategy.device)

        out_buff = strategy.model(mb_x_buff)
        strategy.loss += (1-self.beta_coef) * \
            strategy._criterion(out_buff, mb_y_buff)

        if not self.use_adversarial_replay:
            return

        if self.name_ext_layer is None:
            self.name_ext_layer = get_graph_node_names(strategy.model)[0][-2]

        copy_model = copy.deepcopy(strategy.model)
        feature_extractor = create_feature_extractor(
                copy_model, return_nodes=[self.name_ext_layer])

        params_list = []
        for param_group in strategy.optimizer.state_dict()['param_groups']:
            for i, p in enumerate(copy_model.parameters()):
                if i in param_group['params']:
                    params_list.append(p)

        optimizer = SGD(params_list, lr=self.opt_lr)

        optimizer.zero_grad()
        output = copy_model(strategy.mb_x)
        loss = strategy._criterion(output, strategy.mb_y)
        loss.backward()
        optimizer.step()

        out_curr = feature_extractor(strategy.mb_x)[self.name_ext_layer]
        out_buff = feature_extractor(mb_x_buff)[self.name_ext_layer]

        dist = torch.cdist(out_buff, out_curr)
        _, ind = torch.sort(dist)

        target_attack = torch.zeros(dist.size(0)).long().to(strategy.device)
        for j in range(dist.size(0)):
            for i in ind[j]:
                if mb_y_buff[j].item() != strategy.mb_y[i].item():
                    target_attack[j] = strategy.mb_y[i]

        mb_x_buff.requires_grad = True
        out_pert = copy_model(mb_x_buff)
        loss = strategy._criterion(out_pert, target_attack)
        loss.backward()

        mb_x_pert = self.mifgsm_attack(mb_x_buff, mb_x_buff.grad.data)

        out_buff = strategy.model(mb_x_pert)
        strategy.loss += (1-self.beta_coef) * \
            strategy._criterion(out_buff, mb_y_buff)

    def after_training_exp(self, strategy: "SupervisedTemplate", **kwargs):
        self.storage_policy.update(strategy, **kwargs)

    def get_buffer_batch(self):
        """
        Auxiliary function to obtained the next batch
        """
        iter_replay = iter(self.replay_loader)
        b_batch = next(iter_replay)

        return b_batch

    def mifgsm_attack(self, input, data_grad):
        """
        FGSM - This function generate the perturbation to the input.
        input: Data that we want to apply the perturbation
        data_grad: Gradient of those samples
        """
        pert_out = input
        alpha = self.epsilon_fgsm/self.iter_fgsm
        g = 0
        for i in range(self.iter_fgsm-1):
            g = self.decay_factor_fgsm*g + data_grad/torch.norm(data_grad, p=1)
            pert_out = pert_out + alpha*torch.sign(g)
            pert_out = torch.clamp(pert_out, 0, 1)
            if torch.norm((pert_out-input), p=float('inf')) > self.epsilon_fgsm:
                break   
        return pert_out


__all__ = [
    'MIRPlugin'
]
