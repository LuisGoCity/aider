import os
import unittest
from unittest.mock import MagicMock, patch, call

from aider.commands import Commands


class TestCleanCodeCommand(unittest.TestCase):
    def setUp(self):
        self.io = MagicMock()
        self.coder = MagicMock()
        self.coder.root = "/mock/root"
        self.coder.repo = MagicMock()
        self.commands = Commands(self.coder, self.io)

    def test_no_git_repo(self):
        """Test behavior when no git repository is available"""
        self.coder.repo = None
        self.commands.cmd_clean_code("medium")
        self.io.tool_error.assert_called_once_with("No git repository found.")

    def test_invalid_intensity(self):
        """Test behavior with invalid intensity level"""
        self.commands.cmd_clean_code("invalid")
        self.io.tool_warning.assert_called_once_with(
            "Invalid intensity level: invalid. Using 'medium' instead."
        )

    @patch("os.path.exists")
    @patch("os.path.join")
    def test_no_modified_files(self, mock_join, mock_exists):
        """Test behavior when no modified files are found"""
        self.coder.repo.get_default_branch.return_value = "main"
        self.coder.repo.get_changed_files.return_value = []
        
        self.commands.cmd_clean_code("medium")
        
        self.coder.repo.get_default_branch.assert_called_once()
        self.coder.repo.get_changed_files.assert_called_once_with("main")
        self.io.tool_output.assert_any_call("No modified files found in the current branch.")

    @patch("os.path.exists")
    @patch("os.path.join")
    @patch("builtins.open")
    def test_file_processing(self, mock_open, mock_join, mock_exists):
        """Test processing of modified files"""
        # Setup mocks
        self.coder.repo.get_default_branch.return_value = "main"
        self.coder.repo.get_changed_files.return_value = ["file1.py", "file2.js", "file3.txt"]
        
        mock_join.side_effect = lambda *args: "/".join(args)
        mock_exists.side_effect = lambda path: not path.endswith("file3.txt")
        
        # Mock file content
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.side_effect = ["original1", "original2", "modified1", "modified2"]
        mock_open.return_value = mock_file
        
        # Mock coder's run method to simulate file modification
        self.coder.run.side_effect = lambda prompt: None
        self.coder.get_inchat_relative_files.return_value = ["file1.py", "file2.js"]
        
        # Run the command
        self.commands.cmd_clean_code("high")
        
        # Verify correct files were processed
        self.assertEqual(mock_exists.call_count, 3)
        self.assertEqual(mock_open.call_count, 4)  # 2 files x 2 reads each (before and after)
        
        # Verify coder methods were called
        self.assertEqual(self.coder.add_rel_fname.call_count, 2)
        self.assertEqual(self.coder.run.call_count, 2)
        
        # Verify output messages
        self.io.tool_output.assert_any_call("Found 2 modified code files to clean:")

    @patch("os.path.exists")
    @patch("os.path.join")
    @patch("builtins.open")
    def test_auto_commit(self, mock_open, mock_join, mock_exists):
        """Test auto-commit functionality when enabled"""
        # Setup mocks
        self.coder.repo.get_default_branch.return_value = "main"
        self.coder.repo.get_changed_files.return_value = ["file1.py"]
        self.coder.auto_commits = True
        
        mock_join.side_effect = lambda *args: "/".join(args)
        mock_exists.return_value = True
        
        # Mock file content to simulate modification
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.side_effect = ["original", "modified"]
        mock_open.return_value = mock_file
        
        # Run the command
        self.commands.cmd_clean_code("low")
        
        # Verify commit was attempted
        self.coder.repo.commit.assert_called_once()
        commit_args = self.coder.repo.commit.call_args[0]
        self.assertTrue(commit_args[0].startswith("refactor: Clean code with low intensity"))
        self.assertEqual(commit_args[1], ["file1.py"])

    @patch("os.path.exists")
    @patch("os.path.join")
    @patch("builtins.open")
    def test_error_handling(self, mock_open, mock_join, mock_exists):
        """Test error handling for various edge cases"""
        # Setup mocks
        self.coder.repo.get_default_branch.return_value = "main"
        self.coder.repo.get_changed_files.return_value = ["file1.py", "file2.py"]
        
        mock_join.side_effect = lambda *args: "/".join(args)
        mock_exists.return_value = True
        
        # Mock file operations to raise exceptions
        mock_open.side_effect = [
            MagicMock(),  # First file opens fine
            IOError("Permission denied")  # Second file raises error
        ]
        
        # Run the command
        self.commands.cmd_clean_code("medium")
        
        # Verify error handling
        self.io.tool_warning.assert_called_with("Could not read file2.py: Permission denied, skipping.")

    def test_language_from_extension(self):
        """Test the helper method to get language from extension"""
        test_cases = [
            ('.py', 'Python'),
            ('.js', 'JavaScript'),
            ('.cpp', 'C++'),
            ('.unknown', 'code')
        ]
        
        for ext, expected in test_cases:
            self.assertEqual(self.commands._get_language_from_extension(ext), expected)


if __name__ == "__main__":
    unittest.main()
