from pathlib import Path

import torch
from torch import nn as nn

from readability_classifier.models.base_model import BaseModel


class BertConfig:
    """
    Configuration class to store the configuration of a `BertEmbedding`.
    """

    def __init__(self, **kwargs: dict[str, ...]):
        self.vocab_size = kwargs.get("vocab_size", 30000)
        self.type_vocab_size = kwargs.get("type_vocab_size", 300)
        self.hidden_size = kwargs.get("hidden_size", 768)
        self.hidden_dropout_rate = kwargs.get("hidden_dropout_rate", 0.1)
        self.max_position_embeddings = kwargs.get("max_position_embeddings", 200)


class BertEmbedding(BaseModel):
    """
    A Bert embedding layer.
    """

    def __init__(self, config: BertConfig) -> None:
        super().__init__()
        self.vocab_size = config.vocab_size
        self.hidden_size = config.hidden_size

        # Token embedding
        self.token_embedding = nn.Embedding(self.vocab_size, self.hidden_size)
        self.token_embedding.weight.data.normal_(mean=0.0, std=0.02)

        # Position embedding
        self.position_embedding = nn.Embedding(
            config.max_position_embeddings, config.hidden_size
        )
        nn.init.normal_(self.position_embedding.weight.data, mean=0.0, std=0.02)

        # Token type embedding
        self.token_type_embedding = nn.Embedding(
            config.type_vocab_size, config.hidden_size
        )
        nn.init.normal_(self.token_type_embedding.weight.data, mean=0.0, std=0.02)

        # Layer normalization
        self.layer_norm = nn.LayerNorm(config.hidden_size, eps=1e-12)
        self.dropout = nn.Dropout(config.hidden_dropout_rate)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """
        Forward pass of the model.
        :param inputs: The input tensor.
        :return: The output of the model.
        """
        input_ids, token_type_ids = inputs
        batch_size, sequence_length = input_ids.size()

        # Generate position_ids within the defined range using modulo operation
        position_ids = torch.arange(sequence_length, dtype=torch.long).unsqueeze(0)
        position_ids = position_ids % self.position_embedding.num_embeddings

        # Expand the input ids to the same size as position ids
        if token_type_ids is None:
            token_type_ids = torch.full_like(input_ids, 0)

        # Embeddings
        position_embeddings = self.position_embedding(position_ids.to(input_ids.device))
        token_type_embeddings = self.token_type_embedding(token_type_ids)
        token_embeddings = self.token_embedding(input_ids)

        # Sum all embeddings
        embeddings = token_embeddings + token_type_embeddings + position_embeddings
        embeddings = self.layer_norm(embeddings)
        embeddings = self.dropout(embeddings)
        return embeddings

    @classmethod
    def _build_from_config(cls, params: dict[str, ...], save: Path) -> "BaseModel":
        """
        Build the model from a config.
        :param params: The config.
        :param save: The path to save the model.
        :return: Returns the model.
        """
        return cls(BertConfig(**params))


class SemanticExtractorConfig:
    """
    Configuration class to store the configuration of a `SemanticExtractor`.
    """

    def __init__(self, **kwargs: dict[str, ...]):
        # Must be same as hidden_size in BertConfig
        self.input_size = kwargs.get("input_size", 768)


class SemanticExtractor(BaseModel):
    """
    A semantic extractor model. Also known as BertExtractor.
    The model consists of a Bert embedding layer, a convolutional layer, a max pooling
    layer, another convolutional layer and a BiLSTM layer. Relu is used as the
    activation function.
    The input is a tensor of size (1, 512) and the output is a vector of size 10560.
    """

    def __init__(self, config: SemanticExtractorConfig) -> None:
        """
        Initialize the model.
        """
        super().__init__()

        self.bert_embedding = BertEmbedding.build_from_config()

        # In paper: kernel size not specified
        self.conv1 = nn.Conv1d(
            in_channels=config.input_size, out_channels=32, kernel_size=5
        )

        # Same as in paper
        self.relu = nn.ReLU()

        # Same as in paper
        self.maxpool1 = nn.MaxPool1d(kernel_size=3)

        # In paper: kernel size not specified
        self.conv2 = nn.Conv1d(in_channels=32, out_channels=32, kernel_size=5)

        # In paper: args not specified
        self.bidirectional_lstm = nn.LSTM(32, 32, bidirectional=True, batch_first=True)

    def forward(
        self, token_input: torch.Tensor, segment_input: torch.Tensor
    ) -> torch.Tensor:
        """
        Forward pass of the model.
        :param token_input: The token input tensor.
        :param segment_input: The segment input tensor.
        :return: The output of the model.
        """
        texture_embedded = self.bert_embedding([token_input, segment_input])
        # TODO: adjust dimensions for LSTM
        texture_embedded = texture_embedded.permute(0, 2, 1)
        x = self.relu(self.conv1(texture_embedded))
        x = self.maxpool1(x)
        x = self.relu(self.conv2(x))
        # TODO: adjust dimensions for LSTM
        x = x.permute(0, 2, 1)

        x, _ = self.bidirectional_lstm(x)

        # Flatten the tensor after LSTM
        batch_size, seq_length, channels = x.size()
        x = x.contiguous().view(batch_size, -1)  # Flatten the tensor

        return x

    @classmethod
    def _build_from_config(cls, params: dict[str, ...], save: Path) -> "BaseModel":
        """
        Build the model from a config.
        :param params: The config.
        :param save: The path to save the model.
        :return: Returns the model.
        """
        return cls(SemanticExtractorConfig(**params))