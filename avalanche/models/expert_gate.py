from collections import OrderedDict

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.functional import mse_loss, log_softmax

from torchvision import transforms
import torchvision.models as models

from .utils import FeatureExtractorBackbone

from avalanche.models import MultiTaskModule
from avalanche.models.utils import Flatten
from avalanche.benchmarks.scenarios.generic_scenario import CLExperience


def AE_loss(target, reconstruction):
    """Calculates the MSE loss for the autoencoder by comparing the reconstruction to the pre-processed input. 
    """
    reconstruction_loss = mse_loss(
        input=reconstruction, target=target, reduction="sum")
    return reconstruction_loss


    """The expert autoencoder that determines which expert classifier to select for the incoming data.
    """

    def __init__(self, shape, 
                 latent_dim, 
                 arch="alexnet",
                 pretrained_flag=True,
                 device="cpu",
                 output_layer_name="features"):

        super().__init__()

        # Select pretrained AlexNet for preprocessing input 
        base_template = (models.__dict__[arch](
            pretrained=pretrained_flag).to(device))

        self.feature_module = FeatureExtractorBackbone(
                base_template, "features")

        self.shape = shape

        # Encoder Linear -> ReLU
        flattened_size = torch.Size(shape).numel()
        self.encoder = nn.Sequential(
            Flatten(),
            nn.Linear(flattened_size, latent_dim),
            nn.ReLU()
        )

        # Decoder Linear -> Sigmoid
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, flattened_size), 
            nn.Sigmoid()
        )

    def forward(self, x):

        # Encode input
        x = self.encoder(x)

        # Reconstruction
        x = self.decoder(x)

        return x.view(-1, *self.shape)


class ExpertModel(nn.Module):
    """The expert classifier behind the autoencoder that is trained for a specific task.
    """
    def __init__(self, 
                 num_classes, 
                 arch, 
                 device, 
                 pretrained_flag, 
                 feature_template=None):
        super().__init__()

        self.num_classes = num_classes

        # Select pretrained AlexNet for feature backbone
        base_template = (models.__dict__[arch](
            pretrained=pretrained_flag).to(device))

        # Set the feature module from provided template 
        if (feature_template):
            self.feature_module = feature_template.feature_module

        # Use base template if nothing provided
        else: 
            self.feature_module = FeatureExtractorBackbone(
                base_template, "features")

        # Set avgpool layer
        self.avg_pool = base_template._modules['avgpool']

        # Flattener
        self.flatten = Flatten()

        # Classifier module
        self.classifier_module = base_template._modules['classifier']

        # Customize final layer for  the number of classes in the data
        original_classifier_input_dim = self.classifier_module[-1].in_features
        self.classifier_module[-1] = nn.Linear(
            original_classifier_input_dim, self.num_classes)

    def forward(self, x):
        x = self.feature_module(x)
        x = self.avg_pool(x)
        x = self.flatten(x)
        x = self.classifier_module(x)
        return x


class ExpertGate(nn.Module):
    """Overall parent module that holds the dictionary of expert autoencoders and expert classifiers. 
    def __init__(
        self,
        shape,
        num_classes,
        rel_thresh=0.85,
        arch="alexnet",
        pretrained_flag=True,
        device="cpu",
        output_layer_name="features"
    ):
        super().__init__()

        # Store variables
        self.shape = shape
        self.num_classes = num_classes
        self.rel_thresh = rel_thresh
        self.arch = arch
        self.pretrained_flag = pretrained_flag
        self.device = device

        # Dictionary for autoencoders
        # {task, autoencoder}
        self.autoencoder_dict = nn.ModuleDict()

        # Dictionary for experts
        # {task, expert}
        self.expert_dict = nn.ModuleDict()

        # Initialize an expert with pretrained AlexNet
        self.expert = (
            models.__dict__[arch](pretrained=pretrained_flag)
            .to(device)
            .eval()
        )

    def forward(self, x):
        out = self.expert(x)
        return out
