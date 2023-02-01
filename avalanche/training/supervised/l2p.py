from typing import List, Optional

#import _vision_transformer  # do not remove, or else the registry for custom models will not be "compiled"
import numpy as np
import torch
import torch.nn as nn
from avalanche.training.plugins import EvaluationPlugin
from avalanche.training.plugins.strategy_plugin import SupervisedPlugin
from avalanche.training.templates import SupervisedTemplate
from avalanche.models.vit import create_model
#from timm.models import create_model


MODEL = "vit_base_patch16_224"

class L2PTemplate(SupervisedTemplate):
    """
    Learning to Prompt (L2P) plugin.

    Technique introduced in:
    "Wang, Zifeng, et al. "Learning to prompt for continual learning." 
    Proceedings of the IEEE/CVF Conference on Computer Vision and 
    Pattern Recognition. 2022."

    Implementation based on:
    https://github.com/JH-LEE-KR/l2p-pytorch
    """
    def __init__(
        self,
        model_name: str = MODEL,
        criterion: nn.Module = nn.CrossEntropyLoss(),
        train_mb_size: int = 1,
        train_epochs: int = 1,
        eval_mb_size: Optional[int] = 1,
        device: str = "cpu",
        plugins: Optional[List["SupervisedPlugin"]] = None,
        evaluator: EvaluationPlugin = ...,
        eval_every: int = -1,
        peval_mode: str = "epoch",
        prompt_pool: bool = True,
        pool_size: int = 20,
        prompt_length: int = 5,
        top_k: int = 5,
        prompt_key: bool = True,
        pretrained: bool = True,
        num_classes: int = 29,
        drop_rate: float = 0.1,
        drop_path_rate: float = 0.0,
        drop_block_rate: float = None,
        embedding_key: str = "cls",
        prompt_init: str = "uniform",
        batchwise_prompt: bool = False,
        head_type: str = "prompt",
        use_prompt_mask: bool = False,
        train_prompt_mask: bool = False,
        use_cls_features: bool = True,
        **kwargs,
    ):
        self.num_classes = num_classes
        model = create_model(
            model_name=model_name,
            prompt_pool=prompt_pool,
            pool_size=pool_size,
            prompt_length=prompt_length,
            top_k=top_k,
            prompt_key=prompt_key,
            pretrained=pretrained,
            num_classes=num_classes,
            drop_rate=drop_rate,
            drop_path_rate=drop_path_rate,
            drop_block_rate=drop_block_rate,
            embedding_key=embedding_key,
            prompt_init=prompt_init,
            batchwise_prompt=batchwise_prompt,
            head_type=head_type,
            use_prompt_mask=use_prompt_mask,
        )

        for n, p in model.named_parameters():
            if n.startswith(tuple(["blocks", "patch_embed", "cls_token", "norm", "pos_embed"])):
                p.requires_grad = False

        model.head = torch.nn.Linear(768, num_classes).to(device)

        optimizer = torch.optim.Adam(
            model.parameters(),
            betas=(0.9, 0.999),
            lr=0.01,
        )

        super().__init__(
            model,
            optimizer,
            criterion,
            train_mb_size,
            train_epochs,
            eval_mb_size,
            device,
            plugins,
            evaluator,
            eval_every,
            peval_mode,
        )

        self._criterion = criterion
        self.use_cls_features = use_cls_features
        self.train_prompt_mask = train_prompt_mask
        self.use_mask = True

        if use_cls_features:
            self.original_vit = create_model(
                model_name=model_name,
                pretrained=pretrained,
                num_classes=num_classes,
                drop_rate=drop_rate,
                drop_path_rate=drop_path_rate,
                drop_block_rate=drop_block_rate,
            ).to(device)

            self.original_vit.head = torch.nn.Linear(768, num_classes).to(device)

            for p in self.original_vit.parameters():
                p.requires_grad = False

    def _before_training_exp(self, **kwargs):
        super()._before_training_exp(**kwargs)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            betas=(0.9, 0.999),
            lr=0.01,
        )

    def forward(self):
        if self.use_cls_features:
            with torch.no_grad():
                cls_features = self.original_vit(self.mb_x)["pre_logits"]
        else:
            cls_features = None

        self.res = self.model(
            x=self.mb_x,
            task_id=self.mb_task_id,
            cls_features=cls_features,
            train=self.train_prompt_mask,
        )
        logits = self.res["logits"]

        if self.use_mask:
            mask = self.experience.classes_in_this_experience
            not_mask = np.setdiff1d(np.arange(self.num_classes), mask)
            not_mask = torch.tensor(not_mask, dtype=torch.int64).to(self.device)
            logits = logits.index_fill(dim=1, index=not_mask, value=float("-inf"))

        return logits

    def criterion(self):
        loss = self._criterion(self.mb_output, self.mb_y)
        loss = loss - 0.1 * self.res["reduce_sim"]
        return loss
