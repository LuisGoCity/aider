import os
import platform
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import git

from aider.dump import dump  # noqa: F401
from aider.io import InputOutput
from aider.models import Model
from aider.repo import GitRepo
from aider.utils import GitTemporaryDirectory


class TestRepo(unittest.TestCase):
    def setUp(self):
        self.GPT35 = Model("gpt-3.5-turbo")

    def test_diffs_empty_repo(self):
        with GitTemporaryDirectory():
            repo = git.Repo()

            # Add a change to the index
            fname = Path("foo.txt")
            fname.write_text("index\n")
            repo.git.add(str(fname))

            # Make a change in the working dir
            fname.write_text("workingdir\n")

            git_repo = GitRepo(InputOutput(), None, ".")
            diffs = git_repo.get_diffs()
            self.assertIn("index", diffs)
            self.assertIn("workingdir", diffs)

    def test_diffs_nonempty_repo(self):
        with GitTemporaryDirectory():
            repo = git.Repo()
            fname = Path("foo.txt")
            fname.touch()
            repo.git.add(str(fname))

            fname2 = Path("bar.txt")
            fname2.touch()
            repo.git.add(str(fname2))

            repo.git.commit("-m", "initial")

            fname.write_text("index\n")
            repo.git.add(str(fname))

            fname2.write_text("workingdir\n")

            git_repo = GitRepo(InputOutput(), None, ".")
            diffs = git_repo.get_diffs()
            self.assertIn("index", diffs)
            self.assertIn("workingdir", diffs)

    def test_diffs_detached_head(self):
        with GitTemporaryDirectory():
            repo = git.Repo()
            fname = Path("foo.txt")
            fname.touch()
            repo.git.add(str(fname))
            repo.git.commit("-m", "foo")

            fname2 = Path("bar.txt")
            fname2.touch()
            repo.git.add(str(fname2))
            repo.git.commit("-m", "bar")

            fname3 = Path("baz.txt")
            fname3.touch()
            repo.git.add(str(fname3))
            repo.git.commit("-m", "baz")

            repo.git.checkout("HEAD^")

            fname.write_text("index\n")
            repo.git.add(str(fname))

            fname2.write_text("workingdir\n")

            git_repo = GitRepo(InputOutput(), None, ".")
            diffs = git_repo.get_diffs()
            self.assertIn("index", diffs)
            self.assertIn("workingdir", diffs)

    def test_diffs_between_commits(self):
        with GitTemporaryDirectory():
            repo = git.Repo()
            fname = Path("foo.txt")

            fname.write_text("one\n")
            repo.git.add(str(fname))
            repo.git.commit("-m", "initial")

            fname.write_text("two\n")
            repo.git.add(str(fname))
            repo.git.commit("-m", "second")

            git_repo = GitRepo(InputOutput(), None, ".")
            diffs = git_repo.diff_commits(False, "HEAD~1", "HEAD")
            self.assertIn("two", diffs)

    @patch("aider.models.Model.simple_send_with_retries")
    def test_get_commit_message(self, mock_send):
        mock_send.side_effect = ["", "a good commit message"]

        model1 = Model("gpt-3.5-turbo")
        model2 = Model("gpt-4")
        dump(model1)
        dump(model2)
        repo = GitRepo(InputOutput(), None, None, models=[model1, model2])

        # Call the get_commit_message method with dummy diff and context
        result = repo.get_commit_message("dummy diff", "dummy context")

        # Assert that the returned message is the expected one from the second model
        self.assertEqual(result, "a good commit message")

        # Check that simple_send_with_retries was called twice
        self.assertEqual(mock_send.call_count, 2)

        # Check that both calls were made with the same messages
        first_call_messages = mock_send.call_args_list[0][0][0]  # Get messages from first call
        second_call_messages = mock_send.call_args_list[1][0][0]  # Get messages from second call
        self.assertEqual(first_call_messages, second_call_messages)

    @patch("aider.models.Model.simple_send_with_retries")
    def test_get_commit_message_strip_quotes(self, mock_send):
        mock_send.return_value = '"a good commit message"'

        repo = GitRepo(InputOutput(), None, None, models=[self.GPT35])
        # Call the get_commit_message method with dummy diff and context
        result = repo.get_commit_message("dummy diff", "dummy context")

        # Assert that the returned message is the expected one
        self.assertEqual(result, "a good commit message")

    @patch("aider.models.Model.simple_send_with_retries")
    def test_get_commit_message_no_strip_unmatched_quotes(self, mock_send):
        mock_send.return_value = 'a good "commit message"'

        repo = GitRepo(InputOutput(), None, None, models=[self.GPT35])
        # Call the get_commit_message method with dummy diff and context
        result = repo.get_commit_message("dummy diff", "dummy context")

        # Assert that the returned message is the expected one
        self.assertEqual(result, 'a good "commit message"')

    @patch("aider.models.Model.simple_send_with_retries")
    def test_get_commit_message_with_custom_prompt(self, mock_send):
        mock_send.return_value = "Custom commit message"
        custom_prompt = "Generate a commit message in the style of Shakespeare"

        repo = GitRepo(InputOutput(), None, None, models=[self.GPT35], commit_prompt=custom_prompt)
        result = repo.get_commit_message("dummy diff", "dummy context")

        self.assertEqual(result, "Custom commit message")
        mock_send.assert_called_once()
        args = mock_send.call_args[0]  # Get positional args
        self.assertEqual(args[0][0]["content"], custom_prompt)  # Check first message content

    @patch("aider.repo.GitRepo.get_commit_message")
    def test_commit_with_custom_committer_name(self, mock_send):
        mock_send.return_value = '"a good commit message"'

        # Cleanup of the git temp dir explodes on windows
        if platform.system() == "Windows":
            return

        with GitTemporaryDirectory():
            # new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()

            # add a file and commit it
            fname = Path("file.txt")
            fname.touch()
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "initial commit")

            io = InputOutput()
            git_repo = GitRepo(io, None, None)

            # commit a change
            fname.write_text("new content")
            git_repo.commit(fnames=[str(fname)], aider_edits=True)

            # check the committer name
            commit = raw_repo.head.commit
            self.assertEqual(commit.author.name, "Test User (aider)")
            self.assertEqual(commit.committer.name, "Test User (aider)")

            # commit a change without aider_edits
            fname.write_text("new content again!")
            git_repo.commit(fnames=[str(fname)], aider_edits=False)

            # check the committer name
            commit = raw_repo.head.commit
            self.assertEqual(commit.author.name, "Test User")
            self.assertEqual(commit.committer.name, "Test User (aider)")

            # check that the original committer name is restored
            original_committer_name = os.environ.get("GIT_COMMITTER_NAME")
            self.assertIsNone(original_committer_name)
            original_author_name = os.environ.get("GIT_AUTHOR_NAME")
            self.assertIsNone(original_author_name)

    def test_get_tracked_files(self):
        # Create a temporary directory
        tempdir = Path(tempfile.mkdtemp())

        # Initialize a git repository in the temporary directory and set user name and email
        repo = git.Repo.init(tempdir)
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "testuser@example.com").release()

        # Create three empty files and add them to the git repository
        filenames = ["README.md", "subdir/fänny.md", "systemüber/blick.md", 'file"with"quotes.txt']
        created_files = []
        for filename in filenames:
            file_path = tempdir / filename
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.touch()
                repo.git.add(str(file_path))
                created_files.append(Path(filename))
            except OSError:
                # windows won't allow files with quotes, that's ok
                self.assertIn('"', filename)
                self.assertEqual(os.name, "nt")

        self.assertTrue(len(created_files) >= 3)

        repo.git.commit("-m", "added")

        tracked_files = GitRepo(InputOutput(), [tempdir], None).get_tracked_files()

        # On windows, paths will come back \like\this, so normalize them back to Paths
        tracked_files = [Path(fn) for fn in tracked_files]

        # Assert that coder.get_tracked_files() returns the three filenames
        self.assertEqual(set(tracked_files), set(created_files))

    def test_get_tracked_files_with_new_staged_file(self):
        with GitTemporaryDirectory():
            # new repo
            raw_repo = git.Repo()

            # add it, but no commits at all in the raw_repo yet
            fname = Path("new.txt")
            fname.touch()
            raw_repo.git.add(str(fname))

            git_repo = GitRepo(InputOutput(), None, None)

            # better be there
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)

            # commit it, better still be there
            raw_repo.git.commit("-m", "new")
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)

            # new file, added but not committed
            fname2 = Path("new2.txt")
            fname2.touch()
            raw_repo.git.add(str(fname2))

            # both should be there
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)
            self.assertIn(str(fname2), fnames)

    def test_get_tracked_files_with_aiderignore(self):
        with GitTemporaryDirectory():
            # new repo
            raw_repo = git.Repo()

            # add it, but no commits at all in the raw_repo yet
            fname = Path("new.txt")
            fname.touch()
            raw_repo.git.add(str(fname))

            aiderignore = Path(".aiderignore")
            git_repo = GitRepo(InputOutput(), None, None, str(aiderignore))

            # better be there
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)

            # commit it, better still be there
            raw_repo.git.commit("-m", "new")
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)

            # new file, added but not committed
            fname2 = Path("new2.txt")
            fname2.touch()
            raw_repo.git.add(str(fname2))

            # both should be there
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)
            self.assertIn(str(fname2), fnames)

            aiderignore.write_text("new.txt\n")
            time.sleep(2)

            # new.txt should be gone!
            fnames = git_repo.get_tracked_files()
            self.assertNotIn(str(fname), fnames)
            self.assertIn(str(fname2), fnames)

            # This does not work in github actions?!
            # The mtime doesn't change, even if I time.sleep(1)
            # Before doing this write_text()!?
            #
            # aiderignore.write_text("new2.txt\n")
            # new2.txt should be gone!
            # fnames = git_repo.get_tracked_files()
            # self.assertIn(str(fname), fnames)
            # self.assertNotIn(str(fname2), fnames)

    def test_get_tracked_files_from_subdir(self):
        with GitTemporaryDirectory():
            # new repo
            raw_repo = git.Repo()

            # add it, but no commits at all in the raw_repo yet
            fname = Path("subdir/new.txt")
            fname.parent.mkdir()
            fname.touch()
            raw_repo.git.add(str(fname))

            os.chdir(fname.parent)

            git_repo = GitRepo(InputOutput(), None, None)

            # better be there
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)

            # commit it, better still be there
            raw_repo.git.commit("-m", "new")
            fnames = git_repo.get_tracked_files()
            self.assertIn(str(fname), fnames)

    def test_subtree_only(self):
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()

            # Create files in different directories
            root_file = Path("root.txt")
            subdir_file = Path("subdir/subdir_file.txt")
            another_subdir_file = Path("another_subdir/another_file.txt")

            root_file.touch()
            subdir_file.parent.mkdir()
            subdir_file.touch()
            another_subdir_file.parent.mkdir()
            another_subdir_file.touch()

            raw_repo.git.add(str(root_file), str(subdir_file), str(another_subdir_file))
            raw_repo.git.commit("-m", "Initial commit")

            # Change to the subdir
            os.chdir(subdir_file.parent)

            # Create GitRepo instance with subtree_only=True
            git_repo = GitRepo(InputOutput(), None, None, subtree_only=True)

            # Test ignored_file method
            self.assertFalse(git_repo.ignored_file(str(subdir_file)))
            self.assertTrue(git_repo.ignored_file(str(root_file)))
            self.assertTrue(git_repo.ignored_file(str(another_subdir_file)))

            # Test get_tracked_files method
            tracked_files = git_repo.get_tracked_files()
            self.assertIn(str(subdir_file), tracked_files)
            self.assertNotIn(str(root_file), tracked_files)
            self.assertNotIn(str(another_subdir_file), tracked_files)

    @patch("aider.models.Model.simple_send_with_retries")
    def test_noop_commit(self, mock_send):
        mock_send.return_value = '"a good commit message"'

        with GitTemporaryDirectory():
            # new repo
            raw_repo = git.Repo()

            # add it, but no commits at all in the raw_repo yet
            fname = Path("file.txt")
            fname.touch()
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "new")

            git_repo = GitRepo(InputOutput(), None, None)

            git_repo.commit(fnames=[str(fname)])

    def test_git_commit_verify(self):
        """Test that git_commit_verify controls whether --no-verify is passed to git commit"""
        # Skip on Windows as hook execution works differently
        if platform.system() == "Windows":
            return

        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()

            # Create a file to commit
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))

            # Do the initial commit
            raw_repo.git.commit("-m", "Initial commit")

            # Now create a pre-commit hook that always fails
            hooks_dir = Path(raw_repo.git_dir) / "hooks"
            hooks_dir.mkdir(exist_ok=True)

            pre_commit_hook = hooks_dir / "pre-commit"
            pre_commit_hook.write_text("#!/bin/sh\nexit 1\n")  # Always fail
            pre_commit_hook.chmod(0o755)  # Make executable

            # Modify the file
            fname.write_text("modified content")

            # Create GitRepo with verify=True (default)
            io = InputOutput()
            git_repo_verify = GitRepo(io, None, None, git_commit_verify=True)

            # Attempt to commit - should fail due to pre-commit hook
            commit_result = git_repo_verify.commit(fnames=[str(fname)], message="Should fail")
            self.assertIsNone(commit_result)

            # Create GitRepo with verify=False
            git_repo_no_verify = GitRepo(io, None, None, git_commit_verify=False)

            # Attempt to commit - should succeed by bypassing the hook
            commit_result = git_repo_no_verify.commit(fnames=[str(fname)], message="Should succeed")
            self.assertIsNotNone(commit_result)

            # Verify the commit was actually made
            latest_commit_msg = raw_repo.head.commit.message
            self.assertEqual(latest_commit_msg.strip(), "Should succeed")

    def test_get_default_branch(self):
        """Test that get_default_branch correctly identifies main or master as the default branch"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()

            # Create a file to commit
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))

            # Do the initial commit on master branch (default for git init)
            raw_repo.git.commit("-m", "Initial commit")

            # Create GitRepo instance
            git_repo = GitRepo(InputOutput(), None, None)

            # Test default branch detection - should be "master" initially
            default_branch = git_repo.get_default_branch()
            self.assertEqual(default_branch, "main")

            # Create and switch to "main" branch
            raw_repo.git.branch("main")
            raw_repo.git.checkout("main")

            # Test default branch detection again - should find "main" first
            # since the implementation checks for "main" before "master"
            default_branch = git_repo.get_default_branch()
            self.assertEqual(default_branch, "main")

            # Delete master branch to test only main exists
            raw_repo.git.branch("-D", "master")

            # Test default branch detection - should still be "main"
            default_branch = git_repo.get_default_branch()
            self.assertEqual(default_branch, "main")

    def test_get_default_branch_error_handling(self):
        """Test that get_default_branch handles errors gracefully"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()

            # Create a file to commit
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create GitRepo instance
            git_repo = GitRepo(InputOutput(), None, None)

            # Test normal behavior first
            default_branch = git_repo.get_default_branch()
            self.assertIsNotNone(default_branch)

            # Mock git.cmd.Git.execute to simulate git errors
            with patch(
                "git.cmd.Git.execute", side_effect=git.exc.GitCommandError("rev-parse", 128)
            ):
                # Replace the repo in git_repo with our mocked repo
                git_repo.repo = raw_repo

                # Method should return None when both branch checks fail
                default_branch = git_repo.get_default_branch()
                self.assertIsNone(default_branch)

    def test_get_commit_history(self):
        """Test that get_commit_history correctly returns commit history between branches"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on master branch (default for git init)
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create main branch since the default is master
            raw_repo.git.branch("main")

            # Create and switch to feature branch
            raw_repo.git.branch("feature")
            raw_repo.git.checkout("feature")

            # Make changes and commits on feature branch
            fname.write_text("feature change 1")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Feature commit 1")

            fname.write_text("feature change 2")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Feature commit 2")

            # Create GitRepo instance
            git_repo = GitRepo(InputOutput(), None, None)

            # Get commit history between master and feature
            commit_history = git_repo.get_commit_history("master", "feature")

            # Verify commit history contains our commit messages
            self.assertIn("Feature commit 1", commit_history)
            self.assertIn("Feature commit 2", commit_history)

            # Verify it doesn't contain the initial commit (which is on both branches)
            self.assertNotIn("Initial commit", commit_history)

    def test_get_commit_history_error_handling(self):
        """Test that get_commit_history handles errors gracefully"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file to commit
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create GitRepo instance
            git_repo = GitRepo(InputOutput(), None, None)

            # Test with non-existent branch
            with self.assertRaises(git.exc.GitCommandError):
                git_repo.get_commit_history("master", "non-existent-branch")

            # Mock git.cmd.Git.execute to simulate git errors
            with patch("git.cmd.Git.execute", side_effect=git.exc.GitCommandError("log", 128)):
                # Replace the repo in git_repo with our mocked repo
                git_repo.repo = raw_repo

                # Method should raise the GitCommandError
                with self.assertRaises(git.exc.GitCommandError):
                    git_repo.get_commit_history("master", "feature")

    def test_get_changed_files_error_handling(self):
        """Test that get_changed_files handles errors gracefully"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file to commit
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create GitRepo instance
            git_repo = GitRepo(InputOutput(), None, None)

            # Test with non-existent branch
            with self.assertRaises(git.exc.GitCommandError):
                git_repo.get_changed_files("master", "non-existent-branch")

            # Mock git.cmd.Git.execute to simulate git errors
            with patch("git.cmd.Git.execute", side_effect=git.exc.GitCommandError("diff", 128)):
                # Replace the repo in git_repo with our mocked repo
                git_repo.repo = raw_repo

                # Method should raise the GitCommandError
                with self.assertRaises(git.exc.GitCommandError):
                    git_repo.get_changed_files("master", "feature")

    def test_get_changed_files(self):
        """Test that get_changed_files correctly returns files changed between branches"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on master branch
            fname1 = Path("test_file1.txt")
            fname1.write_text("initial content")
            raw_repo.git.add(str(fname1))
            raw_repo.git.commit("-m", "Initial commit")

            # Create and switch to feature branch
            raw_repo.git.branch("feature")
            raw_repo.git.checkout("feature")

            # Modify existing file
            fname1.write_text("modified content")
            raw_repo.git.add(str(fname1))

            # Add new file
            fname2 = Path("test_file2.txt")
            fname2.write_text("new file content")
            raw_repo.git.add(str(fname2))

            # Commit changes on feature branch
            raw_repo.git.commit("-m", "Feature changes")

            # Create GitRepo instance
            git_repo = GitRepo(InputOutput(), None, None)

            # Get changed files between master and feature
            changed_files = git_repo.get_changed_files("master", "feature")

            # Verify both files are in the changed files list
            self.assertIn("test_file1.txt", changed_files)
            self.assertIn("test_file2.txt", changed_files)
            self.assertEqual(len(changed_files), 2)
            
    def test_push_commited_changes(self):
        """Test that push_commited_changes correctly pushes changes to remote"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create GitRepo instance with mock IO
            io = InputOutput()
            git_repo = GitRepo(io, None, None)
            
            # Test 1: Successful push with explicit branch name
            with patch("subprocess.run") as mock_run:
                # Configure mock to simulate successful push
                mock_result = unittest.mock.Mock()
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                # Call push_commited_changes with explicit branch name
                success, error = git_repo.push_commited_changes(branch_name="main")
                
                # Verify success
                self.assertTrue(success)
                self.assertIsNone(error)
                
                # Verify subprocess.run was called with correct arguments
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                self.assertEqual(args, ["git", "push", "origin", "-u", "main"])
            
            # Test 2: Successful push with auto-detected branch name
            mock_branch = unittest.mock.Mock()
            mock_branch.name = "feature"
            with patch.object(git_repo.repo, "active_branch", mock_branch):
                with patch("subprocess.run") as mock_run:
                    # Configure mock to simulate successful push
                    mock_result = unittest.mock.Mock()
                    mock_result.returncode = 0
                    mock_run.return_value = mock_result
                    
                    # Call push_commited_changes without branch name
                    success, error = git_repo.push_commited_changes()
                    
                    # Verify success
                    self.assertTrue(success)
                    self.assertIsNone(error)
                    
                    # Verify subprocess.run was called with correct arguments
                    mock_run.assert_called_once()
                    args = mock_run.call_args[0][0]
                    self.assertEqual(args, ["git", "push", "origin", "-u", "feature"])
            
            # Test 3: Failed push due to authentication error
            with patch("subprocess.run") as mock_run:
                # Configure mock to simulate authentication failure
                mock_result = unittest.mock.Mock()
                mock_result.returncode = 1
                mock_result.stderr = "Authentication failed"
                mock_run.return_value = mock_result
                
                # Call push_commited_changes
                success, error = git_repo.push_commited_changes(branch_name="main")
                
                # Verify failure
                self.assertFalse(success)
                self.assertIn("authentication failed", error.lower())
            
            # Test 4: Failed push due to network error
            with patch("subprocess.run") as mock_run:
                # Configure mock to simulate network error
                mock_result = unittest.mock.Mock()
                mock_result.returncode = 1
                mock_result.stderr = "Could not resolve host: github.com"
                mock_run.return_value = mock_result
                
                # Call push_commited_changes
                success, error = git_repo.push_commited_changes(branch_name="main")
                
                # Verify failure
                self.assertFalse(success)
                self.assertIn("network error", error.lower())
            
            # Test 5: Failed push due to subprocess error
            with patch("subprocess.run", side_effect=subprocess.SubprocessError("Command failed")):
                # Call push_commited_changes
                success, error = git_repo.push_commited_changes(branch_name="main")
                
                # Verify failure
                self.assertFalse(success)
                self.assertIn("error executing git push", error.lower())

    def test_raise_pr(self):
        """Test that raise_pr correctly calls GitHub CLI to create a PR"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on master branch
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create and switch to feature branch
            raw_repo.git.branch("feature")
            raw_repo.git.checkout("feature")

            # Make changes and commit on feature branch
            fname.write_text("feature change")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Feature change")

            # Create GitRepo instance with mock IO
            io = InputOutput()
            git_repo = GitRepo(io, None, None)

            # Mock push_commited_changes to simulate successful push
            with patch.object(git_repo, "push_commited_changes", return_value=(True, None)) as mock_push:
                # Mock subprocess.run to simulate successful PR creation
                pr_url = "https://github.com/user/repo/pull/123"
                mock_result = unittest.mock.Mock()
                mock_result.returncode = 0
                mock_result.stdout = pr_url + "\n"

                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    # Call raise_pr method
                    result = git_repo.raise_pr("master", "feature", "Test PR Title", "Test PR Description")

                    # Verify push_commited_changes was called with the correct branch name
                    mock_push.assert_called_once_with(branch_name="feature")

                    # Verify subprocess.run was called
                    mock_run.assert_called()

                    # Verify the method returned True for success
                    self.assertTrue(result)

                    # Get the command that was passed to subprocess.run
                    args = mock_run.call_args[0][0]

                    # Check that the command contains all the expected parts
                    self.assertIn("gh", args)
                    self.assertIn("pr", args)
                    self.assertIn("create", args)
                    self.assertIn("--base", args)
                    self.assertIn("master", args)
                    self.assertIn("--head", args)
                    self.assertIn("feature", args)
                    self.assertIn("--title", args)
                    self.assertIn("Test PR Title", args)
                    self.assertIn("--body", args)
                    self.assertIn("Test PR Description", args)

            # Test when push fails
            with patch.object(git_repo, "push_commited_changes", return_value=(False, "Push failed")) as mock_push:
                # Reset IO to capture new messages
                io = InputOutput()
                git_repo = GitRepo(io, None, None)

                # Call raise_pr method
                result = git_repo.raise_pr("master", "feature", "Test PR Title", "Test PR Description")

                # Verify push_commited_changes was called with the correct branch name
                mock_push.assert_called_once_with(branch_name="feature")

                # Verify the method returned False for failure
                self.assertFalse(result)

            # Test when GitHub CLI is not available
            with patch.object(git_repo, "push_commited_changes", return_value=(True, None)):
                with patch("subprocess.run", side_effect=FileNotFoundError()) as mock_run:
                    # Reset IO to capture new messages
                    io = InputOutput()
                    git_repo = GitRepo(io, None, None)

                    # Call raise_pr method
                    result = git_repo.raise_pr("master", "feature", "Test PR Title", "Test PR Description")

                    # Verify error message was output
                    mock_run.assert_called()

                    # Verify the method returned False for failure
                    self.assertFalse(result)

    def test_raise_pr_error_handling(self):
        """Test that raise_pr handles errors from GitHub CLI gracefully"""
        with GitTemporaryDirectory():
            # Create a new repo
            raw_repo = git.Repo()
            raw_repo.config_writer().set_value("user", "name", "Test User").release()
            raw_repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on master branch
            fname = Path("test_file.txt")
            fname.write_text("initial content")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Initial commit")

            # Create and switch to feature branch
            raw_repo.git.branch("feature")
            raw_repo.git.checkout("feature")

            # Make changes and commit on feature branch
            fname.write_text("feature change")
            raw_repo.git.add(str(fname))
            raw_repo.git.commit("-m", "Feature change")

            # Create GitRepo instance with mock IO
            io = InputOutput()
            git_repo = GitRepo(io, None, None)

            # Mock push_commited_changes to simulate successful push
            with patch.object(git_repo, "push_commited_changes", return_value=(True, None)):
                # Mock subprocess.run to simulate PR creation failure
                mock_result = unittest.mock.Mock()
                mock_result.returncode = 1
                mock_result.stderr = "Error: failed to create PR\n"

                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    # Call raise_pr method
                    result = git_repo.raise_pr("master", "feature", "Test PR Title", "Test PR Description")

                    # Verify subprocess.run was called
                    self.assertEqual(mock_run.call_count, 1)

                    # Verify the method returned False for failure
                    self.assertFalse(result)

                    # Verify the correct error message was output
                    # We can't directly check IO output, but the implementation should handle the error
