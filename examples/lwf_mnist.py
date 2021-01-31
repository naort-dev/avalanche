import torch
import argparse
from avalanche.benchmarks import SplitMNIST
from avalanche.training.strategies import LwF
from avalanche.models import SimpleMLP
from avalanche.evaluation.metrics import TaskForgetting, accuracy_metrics, \
    loss_metrics
from avalanche.logging import InteractiveLogger
from avalanche.training.plugins import EvaluationPlugin


"""
This example tests Learning without Forgetting (LwF) on Split MNIST.
The performance with default arguments should give an average accuracy
of about 73%.
"""

parser = argparse.ArgumentParser()
parser.add_argument('--lwf_alpha', nargs='+', type=float,
                    default=[0, 0.5, 1.333, 2.25, 3.2],
                    help='Penalty hyperparameter for LwF. It can be either'
                         'a list with multiple elements (one alpha per step)'
                         'or a list of one element (same alpha for all steps).')
parser.add_argument('--softmax_temperature', type=float, default=1,
                    help='Temperature for softmax used in distillation')
parser.add_argument('--lr', type=float, default=1e-3, help='Learning rate.')
parser.add_argument('--hs', type=int, default=256, help='MLP hidden size.')
parser.add_argument('--epochs', type=int, default=10, 
                    help='Number of training epochs.')
parser.add_argument('--minibatch_size', type=int, default=128,
                    help='Minibatch size.')
parser.add_argument('--cuda', type=int, default=-1,
                    help='Specify GPU id to use. Use CPU if -1.')
args = parser.parse_args()


model = SimpleMLP(hidden_size=args.hs)
optimizer = torch.optim.SGD(model.parameters(), lr=args.lr)
criterion = torch.nn.CrossEntropyLoss()

# check if selected GPU is available or use CPU
assert args.cuda == -1 or args.cuda >= 0, "cuda must be -1 or >= 0."
if args.cuda >= 0:
    assert torch.cuda.device_count() > args.cuda, \
           f"{args.cuda + 1} GPU needed. Found {torch.cuda.device_count()}."
device = 'cpu' if args.cuda == -1 else f'cuda:{args.cuda}'
print(f'Using device: {device}')

# create split scenario
scenario = SplitMNIST(n_steps=5, return_task_id=False)

interactive_logger = InteractiveLogger()
eval_plugin = EvaluationPlugin(
    accuracy_metrics(minibatch=True, epoch=True, task=True),
    loss_metrics(minibatch=True, epoch=True, task=True),
    TaskForgetting(),
    loggers=[interactive_logger])

# create strategy
assert len(args.lwf_alpha) == 1 or len(args.lwf_alpha) == 5,\
    'Alpha must be a non-empty list.'
lwf_alpha = args.lwf_alpha[0] if len(args.lwf_alpha) == 1 else args.lwf_alpha

strategy = LwF(model, optimizer, criterion, alpha=lwf_alpha,
               temperature=args.softmax_temperature,
               train_epochs=args.epochs, device=device,
               train_mb_size=args.minibatch_size, evaluator=eval_plugin)

# train on the selected scenario with the chosen strategy
print('Starting experiment...')
results = []
for train_batch_info in scenario.train_stream:
    print("Start training on step ", train_batch_info.current_step)

    strategy.train(train_batch_info, num_workers=4)
    print("End training on step ", train_batch_info.current_step)
    print('Computing accuracy on the test set')
    results.append(strategy.test(scenario.test_stream[:]))
