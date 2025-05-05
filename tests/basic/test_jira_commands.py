import os
import pytest
from unittest.mock import patch, MagicMock, ANY

from aider.commands import Commands
from aider.io import InputOutput


class TestJiraCommands:
    @pytest.fixture
    def mock_io(self):
        io = MagicMock(spec=InputOutput)
        io.confirm_ask.return_value = True
        return io

    @pytest.fixture
    def mock_coder(self):
        coder = MagicMock()
        coder.repo = MagicMock()
        return coder

    @pytest.fixture
    def commands(self, mock_io, mock_coder):
        commands = Commands(mock_io)
        commands.coder = mock_coder
        return commands

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    @patch("aider.commands.os.remove")
    def test_solve_jira_commits_implementation_plan(
        self, mock_remove, mock_exists, mock_jira_class, commands, mock_coder
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks
        mock_exists.return_value = True
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify implementation plan was committed
        mock_coder.repo.repo.git.add.assert_any_call("jira_issue_TEST-123_implementation_plan.md")
        mock_coder.repo.commit.assert_any_call(
            fnames=["jira_issue_TEST-123_implementation_plan.md"],
            message="Add implementation plan for JIRA issue TEST-123",
            aider_edits=True
        )

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    @patch("aider.commands.os.remove")
    def test_solve_jira_deletes_implementation_plan(
        self, mock_remove, mock_exists, mock_jira_class, commands, mock_coder
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks
        mock_exists.return_value = True
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify implementation plan was deleted and the deletion was committed
        mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")
        mock_coder.repo.repo.git.add.assert_any_call("jira_issue_TEST-123_implementation_plan.md")
        mock_coder.repo.commit.assert_any_call(
            fnames=["jira_issue_TEST-123_implementation_plan.md"],
            message="Remove implementation plan for JIRA issue TEST-123",
            aider_edits=True
        )

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    @patch("aider.commands.os.remove")
    def test_solve_jira_deletes_ticket_file(
        self, mock_remove, mock_exists, mock_jira_class, commands, mock_coder
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks
        mock_exists.return_value = True
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify ticket file was deleted and the deletion was committed
        mock_remove.assert_any_call("jira_issue_TEST-123.txt")
        mock_coder.repo.repo.git.add.assert_any_call("jira_issue_TEST-123.txt")
        mock_coder.repo.commit.assert_any_call(
            fnames=["jira_issue_TEST-123.txt"],
            message="Remove JIRA ticket file for issue TEST-123",
            aider_edits=True
        )

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    @patch("aider.commands.os.remove")
    def test_solve_jira_with_pr_flag(
        self, mock_remove, mock_exists, mock_jira_class, commands, mock_coder
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks
        mock_exists.return_value = True
        
        # Mock the cmd_raise_pr method
        commands.cmd_raise_pr = MagicMock()
        
        # Execute the command with PR flag
        commands.cmd_solve_jira("TEST-123 --with-pr")
        
        # Verify PR was raised after file deletions
        commands.cmd_raise_pr.assert_called_once()

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    def test_solve_jira_handles_missing_files(
        self, mock_exists, mock_jira_class, commands, mock_io
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks - files don't exist
        mock_exists.return_value = False
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify appropriate error messages were shown
        mock_io.tool_error.assert_any_call("Implementation plan file not found: jira_issue_TEST-123_implementation_plan.md")

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    @patch("aider.commands.os.remove")
    def test_solve_jira_handles_git_errors(
        self, mock_remove, mock_exists, mock_jira_class, commands, mock_coder, mock_io
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks
        mock_exists.return_value = True
        
        # Make git operations fail
        mock_coder.repo.repo.git.add.side_effect = Exception("Git error")
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify error handling
        mock_io.tool_error.assert_any_call(ANY)

    @patch("aider.commands.Jira")
    def test_solve_jira_handles_jira_errors(
        self, mock_jira_class, commands, mock_io
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.side_effect = ValueError("JIRA API error")
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify error handling
        mock_io.tool_error.assert_any_call("JIRA API error: JIRA API error")

    @patch("aider.commands.Jira")
    @patch("aider.commands.os.path.exists")
    @patch("aider.commands.os.remove")
    def test_solve_jira_handles_file_errors(
        self, mock_remove, mock_exists, mock_jira_class, commands, mock_io
    ):
        # Setup mocks
        mock_jira = MagicMock()
        mock_jira_class.return_value = mock_jira
        mock_jira.get_issue_content.return_value = {
            "key": "TEST-123",
            "fields": {"summary": "Test Issue", "description": "Test Description"}
        }
        
        # Mock file existence checks
        mock_exists.return_value = True
        
        # Make file operations fail
        mock_remove.side_effect = OSError("File error")
        
        # Execute the command
        commands.cmd_solve_jira("TEST-123")
        
        # Verify error handling
        mock_io.tool_error.assert_any_call(ANY)
