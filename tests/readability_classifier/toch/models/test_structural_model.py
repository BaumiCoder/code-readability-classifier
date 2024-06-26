import unittest

from src.readability_classifier.toch.models.structural_model import StructuralModel
from tests.readability_classifier.toch.extractors.test_structural_extractor import (
    create_test_data,
)


class TestStructuralModel(unittest.TestCase):
    structural_model = StructuralModel.build_from_config()

    @unittest.skip(
        "Torch is not supported anymore. Problems with create_test_data() on GPU."
    )
    def test_forward_pass(self):
        # Create test input data
        structural_input_data = create_test_data()

        # Run the forward pass
        output = self.structural_model(structural_input_data)

        # Check the output shape
        assert output.shape == (1, 1)
