import torch
from avalanche.models.dynamic_modules import (
    MultiTaskModule,
    MultiHeadClassifier,
)


class BiCAdapter(torch.nn.Module):
    def __init__(self, model) -> None:
        super().__init__()

        self.model = model
        self.bias_layers = []

    def add_bias_layer(self, device, cls):
        self.bias_layers.append(BiasLayer(device, cls, False))
    
    def forward(self, x):
        out = self.model(x)

        for layer in self.bias_layers:
            out = layer(out)
        
        return out

    def forward_logits(self, x):
        return self.model(x)


class BiCAdapterMH(MultiTaskModule):
    def __init__(self, model) -> None:
        super().__init__()

        self.model = model
        self.bias_layers = []

        out_weights = model.fc.out_features
        in_features = model.fc.in_features
        self.model.fc = MultiHeadClassifier(in_features, 
                                initial_out_features=out_weights)

    def add_bias_layer(self, device, cls):
        self.bias_layers.append(BiasLayer(device, cls, True))
    
    def forward_single_task(self, x, task_label):
        out = self.model.forward_rep(x)
        out = self.model.fc(out, task_label)
        
        if isinstance(task_label, int):
            return self.bias_layers[task_label](out)
        else:
            unique_tasks = torch.unique(task_label)

            out = torch.zeros_like(out)

            for task in unique_tasks:
                task_mask = task_label == task
                x_task = out[task_mask]
                out[task_mask] = self.bias_layers[task](x_task)
            return out

    def forward_logits(self, x):
        return self.model(x)


class BiasLayer(torch.nn.Module):
    """Bias layers with alpha and beta parameters"""

    def __init__(self, device, cls, task_incremental=False):
        super().__init__()
        self.alpha = torch.nn.Parameter(torch.ones(1, device=device))
        self.beta = torch.nn.Parameter(torch.zeros(1, device=device))

        self.cls = torch.Tensor(list(cls)).long().to(device)
        self.not_cls = None
        self.device = device
        self.task_incremental = task_incremental

    def forward(self, x):
        if self.task_incremental:
            return self.alpha * x + self.beta
        else:
            tmp = torch.zeros_like(x)
            tmp[:, self.cls] += x[:, self.cls] * self.alpha + self.beta

            if self.not_cls is None:
                self.not_cls = torch.Tensor([i for i in range(x.size(1)) if i not in self.cls]).long()
                
            tmp[:, self.not_cls] += x[:, self.not_cls]

            return tmp
