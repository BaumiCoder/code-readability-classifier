import os

import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import BertModel, BertTokenizer

MAX_TOKEN_LENGTH = 512
DEFAULT_BATCH_SIZE = 32


class ReadabilityDataset(Dataset):
    def __init__(self, data, labels):
        self.data = data
        self.labels = labels

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx], self.labels[idx]


class CNNModel(nn.Module):
    def __init__(self, num_classes):
        super().__init__()

        # Bert embedding
        self.bert = BertModel.from_pretrained("bert-base-uncased")

        # Convolutional layers
        self.conv1 = nn.Conv2d(in_channels=1, out_channels=32, kernel_size=(3, 768))
        self.conv2 = nn.Conv2d(in_channels=32, out_channels=64, kernel_size=(3, 1))

        # Max-pooling layers
        self.pool = nn.MaxPool2d(kernel_size=(2, 1))

        # Fully connected layers
        self.fc1 = nn.Linear(64 * 49, 128)  # TODO: Adjust
        self.fc2 = nn.Linear(128, num_classes)

        # Dropout layer to reduce overfitting
        self.dropout = nn.Dropout(0.5)

    def forward(self, x):
        # Bert embedding
        x = self.bert(x)[0]

        # Apply convolutional and pooling layers
        x = self.pool(nn.functional.relu(self.conv1(x)))
        x = self.pool(nn.functional.relu(self.conv2(x)))

        # Flatten the feature map
        x = x.view(-1, 64 * 49)  # TODO: Adjust

        # Apply fully connected layers with dropout
        x = self.dropout(nn.functional.relu(self.fc1(x)))
        x = self.fc2(x)

        return x


class CodeReadabilityClassifier:
    def __init__(
        self, batch_size=DEFAULT_BATCH_SIZE, num_epochs=10, learning_rate=0.001
    ):
        self.batch_size = batch_size
        self.num_epochs = num_epochs
        self.learning_rate = learning_rate
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.train_loader = None
        self.test_loader = None

    def prepare_data(self, csv, data_dir):
        """
        Loads the data and prepares it for training and evaluation.
        :param csv: Path to the CSV file containing the scores.
        :param data_dir: Path to the directory containing the code snippets.
        :return: None
        """
        # Load data
        aggregated_scores, code_snippets = self.load_data(csv, data_dir)

        # Tokenize and encode code snippets
        embeddings = {
            name: self.tokenize_and_encode(code) for name, code in code_snippets.items()
        }

        # Combine embeddings (x) and scores (y) into a dictionary
        data = {embeddings[name]: aggregated_scores[name] for name in code_snippets}

        # Split into training and test data
        x_train, x_test, y_train, y_test = train_test_split(
            list(data.keys()), list(data.values()), test_size=0.2
        )

        # Convert the split data to a ReadabilityDatasets
        train_dataset = ReadabilityDataset(x_train, y_train)
        test_dataset = ReadabilityDataset(x_test, y_test)

        # Create data loaders
        self.train_loader = DataLoader(
            train_dataset, batch_size=self.batch_size, shuffle=True
        )
        self.test_loader = DataLoader(
            test_dataset, batch_size=self.batch_size, shuffle=False
        )

        self.setup_model()

    def load_data(self, csv, data_dir):
        mean_scores = self._load_mean_scores(csv)
        code_snippets = self._load_code_snippets(data_dir)

        return mean_scores, code_snippets

    def _load_code_snippets(self, data_dir):
        """
        Loads the code snippets from the files to a dictionary. The file names are used
        as keys and the code snippets as values.
        :param data_dir: Path to the directory containing the code snippets.
        :return: The code snippets as a dictionary.
        """
        code_snippets = {}

        for file in os.listdir(data_dir):
            with open(os.path.join(data_dir, file)) as f:
                # Replace "1.jsnp" with "Snippet1" etc. to match file names in the CSV
                file_name = file.split(".")[0]
                file_name = f"Snippet{file_name}"
                code_snippets[file_name] = f.read()

        return code_snippets

    def _load_mean_scores(self, csv):
        """
        Loads the mean scores from the CSV file.
        :param csv: Path to the CSV file containing the scores.
        :return: A pandas Series containing the mean scores.
        """
        data_frame = pd.read_csv(csv)

        # Drop the first column, which contains evaluator names
        data_frame = data_frame.drop(columns=data_frame.columns[0], axis=1)

        # Calculate the mean of the scores for each code snippet
        data_frame = data_frame.mean(axis=0)

        # Turn into dictionary with file names as keys and mean scores as values
        return data_frame.to_dict()

    def tokenize_and_encode(self, text):
        tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        input_ids = tokenizer.encode(
            text, add_special_tokens=True, truncation=True, max_length=MAX_TOKEN_LENGTH
        )
        input_ids = torch.tensor(input_ids).unsqueeze(0)  # TODO: Add batch dimension?
        return input_ids

    def setup_model(self):
        self.model = CNNModel(2)
        self.model.to(self.device)
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

    def _train_iteration(self, x_batch, y_batch):
        self.optimizer.zero_grad()
        outputs = self.model(x_batch)
        loss = self.criterion(outputs, y_batch)
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def train(self):
        """
        Trains the model.
        :return: None
        """
        for epoch in range(self.num_epochs):
            self.model.train()
            running_loss = 0.0

            # Iterate over the training dataset in mini-batches
            for _batch_idx, (inputs, labels) in enumerate(self.train_loader):
                inputs, labels = inputs.to(self.device), labels.to(self.device)

                loss = self._train_iteration(inputs, labels)
                running_loss += loss

            print(
                f"Epoch {epoch + 1}/{self.num_epochs}, "
                f"Loss: {running_loss / len(self.train_loader)}"
            )

    def evaluate(self):
        self.model.eval()
        with torch.no_grad():
            x_batch, y_batch = next(iter(self.test_loader))
            x_batch, y_batch = x_batch.to(self.device), y_batch.to(self.device)
            predictions = self.model(x_batch)

        mse = mean_squared_error(y_batch.cpu().numpy(), predictions.cpu().numpy())
        print(f"Mean Squared Error (MSE): {mse}")


if __name__ == "__main__":
    data_dir = (
        "C:/Users/lukas/Meine Ablage/Uni/{SoSe23/Masterarbeit/"
        "Datasets/Dataset/Dataset_test/"
    )
    snippets_dir = os.path.join(data_dir, "Snippets")
    csv = os.path.join(data_dir, "scores.csv")

    classifier = CodeReadabilityClassifier()
    classifier.prepare_data(csv, snippets_dir)
    classifier.train()
    classifier.evaluate()
