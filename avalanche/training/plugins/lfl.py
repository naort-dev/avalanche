import copy

import torch

from avalanche.training.plugins.strategy_plugin import StrategyPlugin
from avalanche.training.utils import get_last_fc_layer, freeze_everything


class LFLPlugin(StrategyPlugin):

    def __init__(self, lambda_e):
        """
        :param lambda_e: Euclidean loss hyper parameter
        """
        super().__init__()

        self.lambda_e = lambda_e
        self.prev_model = None

    def _euclidean_loss(self, features, prev_features):
        """
        Compute euclidean loss
        """
        return torch.nn.functional.mse_loss(features, prev_features)

    def penalty(self, x, model, lambda_e):
        """
        Compute weighted euclidean loss
        """
        if self.prev_model is None:
            return 0
        else:
            features, prev_features = self.compute_features(model, x)
            dist_loss = self._euclidean_loss(features, prev_features)
            return lambda_e * dist_loss

    def compute_features(self, model, x):
        """
        Compute features from prev model and current model
        """
        model.eval()
        self.prev_model.eval()

        x = x.contiguous()
        x = x.view(x.size(0), 28*28)
        features = model.features(x)
        prev_features = self.prev_model.features(x)

        return features, prev_features

    def before_backward(self, strategy, **kwargs):
        """
        Add euclidean loss between prev and current features
        """
        lambda_e = self.lambda_e[strategy.training_exp_counter] \
            if isinstance(self.lambda_e, (list, tuple)) else self.lambda_e

        penalty = self.penalty(strategy.mb_x, strategy.model, lambda_e)
        strategy.loss += penalty

    def after_training_exp(self, strategy, **kwargs):
        """
        Save a copy of the model after each experience
        and freeze the prev model and freeze the last layer of current model
        """

        self.prev_model = copy.deepcopy(strategy.model)

        freeze_everything(self.prev_model)

        last_fc_name, last_fc = get_last_fc_layer(strategy.model)

        for param in last_fc.parameters():
            param.requires_grad = False
