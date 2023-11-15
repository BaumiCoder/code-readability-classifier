import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import time

import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from readability_classifier.models.encoders.dataset_encoder import DatasetEncoder
from readability_classifier.utils.config import DEFAULT_MODEL_BATCH_SIZE, ModelInput
from readability_classifier.utils.utils import save_content_to_file


class BaseClassifier(ABC):
    def __init__(
        self,
        model: nn.Module = None,
        criterion: nn.Module = None,
        optimizer: torch.optim.Optimizer = None,
        train_loader: DataLoader = None,
        test_loader: DataLoader = None,
        validation_loader: DataLoader = None,
        store_dir: Path = None,
        batch_size: int = DEFAULT_MODEL_BATCH_SIZE,
        num_epochs: int = 20,
        learning_rate: float = 0.0015,
    ):
        """
        Initializes the classifier.
        :param model: The model.
        :param criterion: The loss function.
        :param train_loader: The data loader for the training data.
        :param test_loader: The data loader for the test data.
        :param validation_loader: The data loader for the validation data.
        :param batch_size: The batch size.
        :param num_epochs: The number of epochs.
        :param learning_rate: The learning rate.
        """
        self.model = model
        self.criterion = criterion
        self.optimizer = optimizer
        self.train_loader = train_loader
        self.test_loader = test_loader
        self.validation_loader = validation_loader
        self.store_dir = store_dir
        self.batch_size = batch_size
        self.num_epochs = num_epochs
        self.learning_rate = learning_rate
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Move model to device
        self.model.to(self.device)

    def fit(self):
        """
        Trains the model.
        :return: None
        """
        if self.train_loader is None:
            raise ValueError("No training data provided.")

        if self.test_loader is None:
            raise ValueError("No test data provided.")

        train_stats = TrainStats(0, [])
        best_test_loss = float("inf")

        for epoch in range(self.num_epochs):
            train_loss = self._fit_epoch()
            test_loss = self._eval_epoch()

            # Update stats
            epoch_stats = EpochStats(epoch + 1, train_loss, test_loss)
            train_stats.epoch_stats.append(epoch_stats)

            # Log the loss
            logging.info(
                f"Epoch {epoch + 1:02}/{self.num_epochs:02}\n"
                f"Train loss: {train_loss:.4f}\n"
                f"Train PPL:  {math.exp(train_loss):7.4f}\n"
                f"Test  loss: {test_loss:.4f}\n"
                f"Test  PPL:  {math.exp(test_loss):7.4f}"
            )

            # Save the model
            self.store(epoch=epoch + 1)

            # Update best model
            if test_loss < best_test_loss:
                best_test_loss = test_loss
                train_stats.best_epoch = epoch + 1
                self.store(path=self.store_dir / Path("best_model.pt"))

        # Save the training stats
        save_content_to_file(
            train_stats.to_json(),
            self.store_dir / Path("train_stats.json"),
        )

        logging.info("Training done.")

    def _fit_batch(self, inp: ModelInput, y_batch: Tensor) -> float:
        """
        Performs a single training iteration.
        :param inp: The input of the model as batch.
        :return: The loss of the batch.
        """
        self.optimizer.zero_grad()
        outputs = self.model(inp)
        loss = self.criterion(outputs, y_batch)
        loss.backward()
        self.optimizer.step()
        return loss.item()

    @abstractmethod
    def _fit_epoch(self) -> float:
        """
        Trains a single epoch.
        :return: The train loss of the epoch.
        """
        pass

    @abstractmethod
    def _eval_epoch(self) -> float:
        """
        Evaluates the model on the test data.
        :return: The validation loss.
        """
        pass

    def _eval_batch(
        self,
        inp: ModelInput,
        y_batch: Tensor,
    ) -> float:
        """
        Evaluates a single batch of the test loader.
        :param inp: The input of the model as batch.
        :param y_batch: The scores of the batch.
        :return: The loss of the batch.
        """
        outputs = self.model(inp)
        loss = self.criterion(outputs, y_batch)
        return loss.item()

    @abstractmethod
    def evaluate(self) -> None:
        """
        Evaluates the model on the validation data.
        :return: The MSE of the model on the validation data.
        """
        pass

    def _extract(self, batch):
        matrix = batch["matrix"].to(self.device)
        input_ids = batch["input_ids"].to(self.device)
        token_type_ids = batch["token_type_ids"].to(self.device)
        image = batch["image"].to(self.device)
        score = batch["score"].unsqueeze(1).to(self.device)
        return matrix, input_ids, token_type_ids, image, score

    def store(self, path: str = None, epoch: int = None) -> None:
        """
        Stores the model at the given path.
        :param path: The path to store the model.
        :param epoch: The epoch to store the model at.
        :return: None
        """
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if path is None and epoch is None:
            path = self.store_dir / Path(f"model_{current_time}.pt")
        elif path is None:
            path = self.store_dir / Path(f"model_{current_time}_{epoch}.pt")

        torch.save(self.model.state_dict(), path)
        logging.info(f"Model stored at {path}")

    def load(self, path: str) -> None:
        """
        Loads the model from the given path.
        :param path: The path to load the model from.
        :return: None
        """
        self.model.load_state_dict(torch.load(path))
        logging.info(f"Model loaded from {path}")

    def predict(self, code_snippet: str) -> float:
        """
        Predicts the readability of the given code snippet.
        :param code_snippet: The code snippet to predict the readability of.
        :return: The predicted readability.
        """
        self.model.eval()

        # Encode the code snippet
        encoder = DatasetEncoder()
        encoded_text = encoder.encode_text(code_snippet)
        matrix = encoded_text["matrix"]
        input_ids = encoded_text["input_ids"]
        token_type_ids = encoded_text["token_type_ids"]
        image = encoded_text["image"]

        # Predict the readability
        with torch.no_grad():
            matrix = matrix.to(self.device)
            input_ids = input_ids.to(self.device)
            token_type_ids = token_type_ids.to(self.device)
            image = image.to(self.device)
            prediction = self.model(matrix, input_ids, token_type_ids, image)
            return prediction.item()


@dataclass(frozen=True, eq=True)
class EpochStats:
    """
    Data class for epoch stats.
    """

    epoch: int
    train_loss: float
    test_loss: float

    def to_json(self) -> str:
        """
        Convert to json.
        :return: Returns the json string.
        """
        return json.dumps(asdict(self))


@dataclass(eq=True)
class TrainStats:
    """
    Data class for training stats.
    """

    best_epoch: int
    epoch_stats: list[EpochStats]
    start_time: int = int(time())
    end_time: int = int(time())

    def to_json(self) -> str:
        """
        Convert to json.
        :return: Returns the json string.
        """
        # Update end time every time when stats are saved
        self.end_time = int(time())
        return json.dumps(asdict(self))