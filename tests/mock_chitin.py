"""Mock Chitin engine for testing."""

from unittest.mock import Mock
import sys

# Create a mock chitin module
mock_chitin = type(sys)("chitin")
mock_chitin.Engine = Mock

# Insert it into sys.modules before any imports
sys.modules["chitin"] = mock_chitin
