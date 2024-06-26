from pathlib import Path

import torch
from torch import nn as nn

from src.readability_classifier.utils.config import StructuralInput
from src.readability_classifier.toch.base_model import BaseModel


class StructuralExtractorConfig:
    """
    The config for the StructuralExtractor.
    """

    def __init__(self, **kwargs) -> None:
        """
        Initialize the config.
        """
        pass


class StructuralExtractor(BaseModel):
    """
    A structural extractor model. Also known as MatrixExtractor.
    The model consists of alternating 2D convolution and max-pooling layers plus a
    flatten layer.
    The input is a tensor of size (1, 305, 50) and the output is a vector of size 41472.
    """

    def __init__(self, config: StructuralExtractorConfig) -> None:
        """
        Initialize the model.
        """
        super().__init__()

        # Alternating 2D convolution and max-pooling layers
        self.relu = nn.ReLU()

        # In code: kernel_size=3
        self.conv1 = nn.Conv2d(in_channels=1, out_channels=32, kernel_size=2)

        # In paper: stride not specified
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)

        # In code: kernel_size=3
        self.conv2 = nn.Conv2d(in_channels=32, out_channels=32, kernel_size=2)

        # In paper: stride not specified
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)

        # Same as in paper
        self.conv3 = nn.Conv2d(in_channels=32, out_channels=64, kernel_size=3)

        # In paper: stride not specified
        self.pool3 = nn.MaxPool2d(kernel_size=3, stride=3)

        # Same as in paper
        self.flatten = nn.Flatten()

    def forward(self, x: StructuralInput) -> torch.Tensor:
        """
        Forward pass of the model.
        :param x: The input tensor.
        :return: The output tensor.
        """
        x = x.character_matrix

        # Apply convolutional and pooling layers
        x = x.unsqueeze(1)
        x = self.relu(self.conv1(x))
        x = self.pool1(x)
        x = self.relu(self.conv2(x))
        x = self.pool2(x)
        x = self.relu(self.conv3(x))
        x = self.pool3(x)

        # Flatten the output of the conv layers
        return self.flatten(x)

    @classmethod
    def _build_from_config(cls, params: dict[str, ...], save: Path) -> "BaseModel":
        """
        Build the model from a config.
        :param params: The config.
        :param save: The path to save the model.
        :return: Returns the model.
        """
        return cls(StructuralExtractorConfig(**params))
