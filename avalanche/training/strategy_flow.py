from typing import Optional, Sequence

from torch.nn import Module
from torch.optim import Optimizer
from torch.utils.data import DataLoader

from avalanche.benchmarks.scenarios import IStepInfo, DatasetPart
from avalanche.evaluation import EvalProtocol
from avalanche.training.plugins import StrategyPlugin, EvaluationPlugin


class StrategyFlow:
    def __init__(self, model: Module, criterion, optimizer: Optimizer, train_mb_size: int = 1, train_epochs: int = 1,
                 test_mb_size: int = 'cpu', device=None,
                 evaluation_protocol: Optional[EvalProtocol] = None,
                 plugins: Optional[Sequence[StrategyPlugin]] = None):
        self.model = model
        self.criterion = criterion
        self.optimizer = optimizer
        self.train_epochs = train_epochs
        self.train_mb_size = train_mb_size
        self.test_mb_size = train_mb_size if test_mb_size is None else test_mb_size
        self.device = device

        self.evaluation_plugin = EvaluationPlugin()
        self.evaluation_protocol = evaluation_protocol
        self.plugins = [] if plugins is None else plugins
        self.plugins.append(self.evaluation_plugin)

        # Flow state variables
        self.step_id = None  # test-flow only.
        self.epoch = None
        self.step_info = None
        self.current_data = None
        self.current_dataloader = None
        self.mb_it = None  # train-flow only. minibatch iteration.
        self.mb_x, self.mb_y = None, None
        self.loss = None
        self.logits = None

    def train(self, step_info: IStepInfo, **kwargs):
        self.step_info = step_info
        self.model.train()
        self.model.to(self.device)

        self.current_data = step_info.current_training_set()[0]
        self.adapt_train_dataset(**kwargs)
        self.make_train_dataloader(**kwargs)

        self.before_training(**kwargs)
        self.epoch = 0
        for self.epoch in range(self.train_epochs):
            self.before_training_epoch(**kwargs)
            self.training_epoch(**kwargs)
            self.after_training_epoch(**kwargs)
        self.after_training(**kwargs)

        if self.evaluation_protocol is not None:
            return self.evaluation_plugin.get_train_result()

    def test(self, step_info: IStepInfo, test_part: DatasetPart, **kwargs):
        self._set_initial_test_step_id(step_info, test_part)
        self.step_info = step_info
        self.model.eval()
        self.model.to(self.device)

        self.before_testing(**kwargs)
        while self._has_testing_steps_left(step_info):
            self.current_data = step_info.step_specific_test_set(self.step_id)[0]
            self.adapt_test_dataset(**kwargs)
            self.make_test_dataloader(**kwargs)

            self.before_testing_step(**kwargs)
            self.testing_epoch(**kwargs)
            self.after_testing_step(**kwargs)

            self.step_id += 1
        self.after_testing(**kwargs)

        if self.evaluation_protocol is not None:
            return self.evaluation_plugin.get_test_result()

    def before_training(self, **kwargs):
        for p in self.plugins:
            p.before_training(self, **kwargs)

    def make_train_dataloader(self, num_workers=0, **kwargs):
        self.current_dataloader = DataLoader(self.current_data,
            num_workers=num_workers, batch_size=self.train_mb_size)

    def _set_initial_test_step_id(self, step_info: IStepInfo,
                                  dataset_part: DatasetPart = None):
        # TODO: if we remove DatasetPart this may become unnecessary
        self.step_id = -1
        if dataset_part is None:
            dataset_part = DatasetPart.COMPLETE

        if dataset_part == DatasetPart.CURRENT:
            self.step_id = step_info.current_step
        if dataset_part in [DatasetPart.CUMULATIVE, DatasetPart.OLD,
                            DatasetPart.COMPLETE]:
            self.step_id = 0
        if dataset_part == DatasetPart.FUTURE:
            self.step_id = step_info.current_step + 1

        if self.step_id < 0:
            raise ValueError('Invalid dataset part')

    def _has_testing_steps_left(self, step_info: IStepInfo,
                                test_part: DatasetPart = None):
        # TODO: if we remove DatasetPart this may become unnecessary
        step_id = self.step_id
        if test_part is None:
            test_part = DatasetPart.COMPLETE

        if test_part == DatasetPart.CURRENT:
            return step_id == step_info.current_step
        if test_part == DatasetPart.CUMULATIVE:
            return step_id <= step_info.current_step
        if test_part == DatasetPart.OLD:
            return step_id < step_info.current_step
        if test_part == DatasetPart.FUTURE:
            return step_info.current_step < step_id < step_info.n_steps
        if test_part == DatasetPart.COMPLETE:
            return step_id < step_info.n_steps

        raise ValueError('Invalid dataset part')

    def make_test_dataloader(self, num_workers=0, **kwargs):
        self.current_dataloader = DataLoader(self.current_data,
              num_workers=num_workers, batch_size=self.test_mb_size)

    def adapt_train_dataset(self, **kwargs):
        for p in self.plugins:
            p.adapt_train_dataset(self, **kwargs)

    def before_training_epoch(self, **kwargs):
        for p in self.plugins:
            p.before_training_epoch(self, **kwargs)

    def training_epoch(self, **kwargs):
        for self.mb_it, (self.mb_x, self.mb_y) in enumerate(self.current_dataloader):
            self.before_training_iteration(**kwargs)

            self.optimizer.zero_grad()
            self.mb_x = self.mb_x.to(self.device)
            self.mb_y = self.mb_y.to(self.device)

            # Forward
            self.before_forward(**kwargs)
            self.logits = self.model(self.mb_x)
            self.after_forward(**kwargs)

            # Loss & Backward
            self.loss = self.criterion(self.logits, self.mb_y)
            self.before_backward(**kwargs)
            self.loss.backward()
            self.after_backward(**kwargs)

            # Optimization step
            self.before_update(**kwargs)
            self.optimizer.step()
            self.after_update(**kwargs)

            self.after_training_iteration(**kwargs)

    def before_training_iteration(self, **kwargs):
        for p in self.plugins:
            p.before_training_iteration(self, **kwargs)

    def before_forward(self, **kwargs):
        for p in self.plugins:
            p.before_forward(self, **kwargs)

    def after_forward(self, **kwargs):
        for p in self.plugins:
            p.after_forward(self, **kwargs)

    def before_backward(self, **kwargs):
        for p in self.plugins:
            p.before_backward(self, **kwargs)

    def after_backward(self, **kwargs):
        for p in self.plugins:
            p.after_backward(self, **kwargs)

    def after_training_iteration(self, **kwargs):
        for p in self.plugins:
            p.after_training_iteration(self, **kwargs)

    def before_update(self, **kwargs):
        for p in self.plugins:
            p.before_update(self, **kwargs)

    def after_update(self, **kwargs):
        for p in self.plugins:
            p.after_update(self, **kwargs)

    def after_training_epoch(self, **kwargs):
        for p in self.plugins:
            p.after_training_epoch(self, **kwargs)

    def after_training(self, **kwargs):
        for p in self.plugins:
            p.after_training(self, **kwargs)
        # Reset flow-state variables. They should not be used outside the flow
        self.epoch = None
        self.step_info = None
        self.current_data = None
        self.current_loader = None
        self.mb_it = None
        self.mb_x, self.mb_y = None, None
        self.loss = None
        self.logits = None

    def before_testing(self, **kwargs):
        for p in self.plugins:
            p.before_testing(self, **kwargs)

    def before_testing_step(self, **kwargs):
        for p in self.plugins:
            p.before_testing_step(self, **kwargs)

    def adapt_test_dataset(self, **kwargs):
        for p in self.plugins:
            p.adapt_test_dataset(self, **kwargs)

    def testing_epoch(self, **kwargs):
        for self.mb_it, (self.mb_x, self.mb_y) in enumerate(self.current_dataloader):
            self.before_test_iteration(**kwargs)

            self.mb_x = self.mb_x.to(self.device)
            self.mb_y = self.mb_y.to(self.device)

            self.before_test_forward(**kwargs)
            self.logits = self.model(self.mb_x)
            self.after_test_forward(**kwargs)
            self.loss = self.criterion(self.logits, self.mb_y)

            self.after_test_iteration(**kwargs)

    def after_testing_step(self, **kwargs):
        for p in self.plugins:
            p.after_testing_step(self, **kwargs)

    def after_testing(self, **kwargs):
        for p in self.plugins:
            p.after_testing(self, **kwargs)
        # Reset flow-state variables. They should not be used outside the flow
        self.step_id = None
        self.step_info = None
        self.current_data = None
        self.current_dataloader = None
        self.mb_it = None
        self.mb_x, self.mb_y = None, None
        self.loss = None
        self.logits = None

    def before_test_iteration(self, **kwargs):
        for p in self.plugins:
            p.before_test_iteration(self, **kwargs)

    def before_test_forward(self, **kwargs):
        for p in self.plugins:
            p.before_test_forward(self, **kwargs)

    def after_test_forward(self, **kwargs):
        for p in self.plugins:
            p.after_test_forward(self, **kwargs)

    def after_test_iteration(self, **kwargs):
        for p in self.plugins:
            p.after_test_iteration(self, **kwargs)

