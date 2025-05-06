import codecs
import os
import re
import shutil
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest import TestCase, mock

import git
import pyperclip
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

from aider.coders import Coder
from aider.commands import Commands, SwitchCoder
from aider.dump import dump  # noqa: F401
from aider.io import InputOutput
from aider.models import Model
from aider.repo import GitRepo
from aider.utils import ChdirTemporaryDirectory, GitTemporaryDirectory, make_repo


class TestCommands(TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tempdir = tempfile.mkdtemp()
        os.chdir(self.tempdir)

        self.GPT35 = Model("gpt-3.5-turbo")

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_cmd_add(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Call the cmd_add method with 'foo.txt' and 'bar.txt' as a single string
        commands.cmd_add("foo.txt bar.txt")

        # Check if both files have been created in the temporary directory
        self.assertTrue(os.path.exists("foo.txt"))
        self.assertTrue(os.path.exists("bar.txt"))

    def test_cmd_copy(self):
        # Initialize InputOutput and Coder instances
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Add some assistant messages to the chat history
        coder.done_messages = [
            {"role": "assistant", "content": "First assistant message"},
            {"role": "user", "content": "User message"},
            {"role": "assistant", "content": "Second assistant message"},
        ]

        # Mock pyperclip.copy and io.tool_output
        with (
            mock.patch("pyperclip.copy") as mock_copy,
            mock.patch.object(io, "tool_output") as mock_tool_output,
        ):
            # Invoke the /copy command
            commands.cmd_copy("")

            # Assert pyperclip.copy was called with the last assistant message
            mock_copy.assert_called_once_with("Second assistant message")

            # Assert that tool_output was called with the expected preview
            expected_preview = (
                "Copied last assistant message to clipboard. Preview: Second assistant message"
            )
            mock_tool_output.assert_any_call(expected_preview)

    def test_cmd_copy_with_cur_messages(self):
        # Initialize InputOutput and Coder instances
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Add messages to done_messages and cur_messages
        coder.done_messages = [
            {"role": "assistant", "content": "First assistant message in done_messages"},
            {"role": "user", "content": "User message in done_messages"},
        ]
        coder.cur_messages = [
            {"role": "assistant", "content": "Latest assistant message in cur_messages"},
        ]

        # Mock pyperclip.copy and io.tool_output
        with (
            mock.patch("pyperclip.copy") as mock_copy,
            mock.patch.object(io, "tool_output") as mock_tool_output,
        ):
            # Invoke the /copy command
            commands.cmd_copy("")

            # Assert pyperclip.copy was called with the last assistant message in cur_messages
            mock_copy.assert_called_once_with("Latest assistant message in cur_messages")

            # Assert that tool_output was called with the expected preview
            expected_preview = (
                "Copied last assistant message to clipboard. Preview: Latest assistant message in"
                " cur_messages"
            )
            mock_tool_output.assert_any_call(expected_preview)
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Add only user messages
        coder.done_messages = [
            {"role": "user", "content": "User message"},
        ]

        # Mock io.tool_error
        with mock.patch.object(io, "tool_error") as mock_tool_error:
            commands.cmd_copy("")
            # Assert tool_error was called indicating no assistant messages
            mock_tool_error.assert_called_once_with("No assistant messages found to copy.")

    def test_cmd_copy_pyperclip_exception(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        coder.done_messages = [
            {"role": "assistant", "content": "Assistant message"},
        ]

        # Mock pyperclip.copy to raise an exception
        with (
            mock.patch(
                "pyperclip.copy", side_effect=pyperclip.PyperclipException("Clipboard error")
            ),
            mock.patch.object(io, "tool_error") as mock_tool_error,
        ):
            commands.cmd_copy("")

            # Assert that tool_error was called with the clipboard error message
            mock_tool_error.assert_called_once_with("Failed to copy to clipboard: Clipboard error")

    def test_cmd_add_bad_glob(self):
        # https://github.com/Aider-AI/aider/issues/293

        io = InputOutput(pretty=False, fancy_input=False, yes=False)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        commands.cmd_add("**.txt")

    def test_cmd_add_with_glob_patterns(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create some test files
        with open("test1.py", "w") as f:
            f.write("print('test1')")
        with open("test2.py", "w") as f:
            f.write("print('test2')")
        with open("test.txt", "w") as f:
            f.write("test")

        # Call the cmd_add method with a glob pattern
        commands.cmd_add("*.py")

        # Check if the Python files have been added to the chat session
        self.assertIn(str(Path("test1.py").resolve()), coder.abs_fnames)
        self.assertIn(str(Path("test2.py").resolve()), coder.abs_fnames)

        # Check if the text file has not been added to the chat session
        self.assertNotIn(str(Path("test.txt").resolve()), coder.abs_fnames)

    def test_cmd_add_no_match(self):
        # yes=False means we will *not* create the file when it is not found
        io = InputOutput(pretty=False, fancy_input=False, yes=False)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Call the cmd_add method with a non-existent file pattern
        commands.cmd_add("*.nonexistent")

        # Check if no files have been added to the chat session
        self.assertEqual(len(coder.abs_fnames), 0)

    def test_cmd_add_no_match_but_make_it(self):
        # yes=True means we *will* create the file when it is not found
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        fname = Path("[abc].nonexistent")

        # Call the cmd_add method with a non-existent file pattern
        commands.cmd_add(str(fname))

        # Check if no files have been added to the chat session
        self.assertEqual(len(coder.abs_fnames), 1)
        self.assertTrue(fname.exists())

    def test_cmd_add_drop_directory(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=False)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create a directory and add files to it using pathlib
        Path("test_dir").mkdir()
        Path("test_dir/another_dir").mkdir()
        Path("test_dir/test_file1.txt").write_text("Test file 1")
        Path("test_dir/test_file2.txt").write_text("Test file 2")
        Path("test_dir/another_dir/test_file.txt").write_text("Test file 3")

        # Call the cmd_add method with a directory
        commands.cmd_add("test_dir test_dir/test_file2.txt")

        # Check if the files have been added to the chat session
        self.assertIn(str(Path("test_dir/test_file1.txt").resolve()), coder.abs_fnames)
        self.assertIn(str(Path("test_dir/test_file2.txt").resolve()), coder.abs_fnames)
        self.assertIn(str(Path("test_dir/another_dir/test_file.txt").resolve()), coder.abs_fnames)

        commands.cmd_drop(str(Path("test_dir/another_dir")))
        self.assertIn(str(Path("test_dir/test_file1.txt").resolve()), coder.abs_fnames)
        self.assertIn(str(Path("test_dir/test_file2.txt").resolve()), coder.abs_fnames)
        self.assertNotIn(
            str(Path("test_dir/another_dir/test_file.txt").resolve()), coder.abs_fnames
        )

        # Issue #139 /add problems when cwd != git_root

        # remember the proper abs path to this file
        abs_fname = str(Path("test_dir/another_dir/test_file.txt").resolve())

        # chdir to someplace other than git_root
        Path("side_dir").mkdir()
        os.chdir("side_dir")

        # add it via it's git_root referenced name
        commands.cmd_add("test_dir/another_dir/test_file.txt")

        # it should be there, but was not in v0.10.0
        self.assertIn(abs_fname, coder.abs_fnames)

        # drop it via it's git_root referenced name
        commands.cmd_drop("test_dir/another_dir/test_file.txt")

        # it should be there, but was not in v0.10.0
        self.assertNotIn(abs_fname, coder.abs_fnames)

    def test_cmd_drop_with_glob_patterns(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create test files in root and subdirectory
        subdir = Path("subdir")
        subdir.mkdir()
        (subdir / "subtest1.py").touch()
        (subdir / "subtest2.py").touch()

        Path("test1.py").touch()
        Path("test2.py").touch()
        Path("test3.txt").touch()

        # Add all Python files to the chat session
        commands.cmd_add("*.py")
        initial_count = len(coder.abs_fnames)
        self.assertEqual(initial_count, 2)  # Only root .py files should be added

        # Test dropping with glob pattern
        commands.cmd_drop("*2.py")
        self.assertIn(str(Path("test1.py").resolve()), coder.abs_fnames)
        self.assertNotIn(str(Path("test2.py").resolve()), coder.abs_fnames)
        self.assertEqual(len(coder.abs_fnames), initial_count - 1)

    def test_cmd_drop_without_glob(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create test files
        test_files = ["file1.txt", "file2.txt", "file3.py"]
        for fname in test_files:
            Path(fname).touch()

        # Add all files to the chat session
        for fname in test_files:
            commands.cmd_add(fname)

        initial_count = len(coder.abs_fnames)
        self.assertEqual(initial_count, 3)

        # Test dropping individual files without glob
        commands.cmd_drop("file1.txt")
        self.assertNotIn(str(Path("file1.txt").resolve()), coder.abs_fnames)
        self.assertIn(str(Path("file2.txt").resolve()), coder.abs_fnames)
        self.assertEqual(len(coder.abs_fnames), initial_count - 1)

        # Test dropping multiple files without glob
        commands.cmd_drop("file2.txt file3.py")
        self.assertNotIn(str(Path("file2.txt").resolve()), coder.abs_fnames)
        self.assertNotIn(str(Path("file3.py").resolve()), coder.abs_fnames)
        self.assertEqual(len(coder.abs_fnames), 0)

    def test_cmd_add_bad_encoding(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create a new file foo.bad which will fail to decode as utf-8
        with codecs.open("foo.bad", "w", encoding="iso-8859-15") as f:
            f.write("ÆØÅ")  # Characters not present in utf-8

        commands.cmd_add("foo.bad")

        self.assertEqual(coder.abs_fnames, set())

    def test_cmd_git(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)

        with GitTemporaryDirectory() as tempdir:
            # Create a file in the temporary directory
            with open(f"{tempdir}/test.txt", "w") as f:
                f.write("test")

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Run the cmd_git method with the arguments "commit -a -m msg"
            commands.cmd_git("add test.txt")
            commands.cmd_git("commit -a -m msg")

            # Check if the file has been committed to the repository
            repo = git.Repo(tempdir)
            files_in_repo = repo.git.ls_files()
            self.assertIn("test.txt", files_in_repo)

    def test_cmd_tokens(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        commands.cmd_add("foo.txt bar.txt")

        # Redirect the standard output to an instance of io.StringIO
        stdout = StringIO()
        sys.stdout = stdout

        commands.cmd_tokens("")

        # Reset the standard output
        sys.stdout = sys.__stdout__

        # Get the console output
        console_output = stdout.getvalue()

        self.assertIn("foo.txt", console_output)
        self.assertIn("bar.txt", console_output)

    def test_cmd_add_from_subdir(self):
        repo = git.Repo.init()
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "testuser@example.com").release()

        # Create three empty files and add them to the git repository
        filenames = ["one.py", Path("subdir") / "two.py", Path("anotherdir") / "three.py"]
        for filename in filenames:
            file_path = Path(filename)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
            repo.git.add(str(file_path))
        repo.git.commit("-m", "added")

        filenames = [str(Path(fn).resolve()) for fn in filenames]

        ###

        os.chdir("subdir")

        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # this should get added
        commands.cmd_add(str(Path("anotherdir") / "three.py"))

        # this should add one.py
        commands.cmd_add("*.py")

        self.assertIn(filenames[0], coder.abs_fnames)
        self.assertNotIn(filenames[1], coder.abs_fnames)
        self.assertIn(filenames[2], coder.abs_fnames)

    def test_cmd_add_from_subdir_again(self):
        with GitTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            Path("side_dir").mkdir()
            os.chdir("side_dir")

            # add a file that is in the side_dir
            with open("temp.txt", "w"):
                pass

            # this was blowing up with GitCommandError, per:
            # https://github.com/Aider-AI/aider/issues/201
            commands.cmd_add("temp.txt")

    def test_cmd_commit(self):
        with GitTemporaryDirectory():
            fname = "test.txt"
            with open(fname, "w") as f:
                f.write("test")
            repo = git.Repo()
            repo.git.add(fname)
            repo.git.commit("-m", "initial")

            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            self.assertFalse(repo.is_dirty())
            with open(fname, "w") as f:
                f.write("new")
            self.assertTrue(repo.is_dirty())

            commit_message = "Test commit message"
            commands.cmd_commit(commit_message)
            self.assertFalse(repo.is_dirty())

    def test_cmd_add_from_outside_root(self):
        with ChdirTemporaryDirectory() as tmp_dname:
            root = Path("root")
            root.mkdir()
            os.chdir(str(root))

            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            outside_file = Path(tmp_dname) / "outside.txt"
            outside_file.touch()

            # This should not be allowed!
            # https://github.com/Aider-AI/aider/issues/178
            commands.cmd_add("../outside.txt")

            self.assertEqual(len(coder.abs_fnames), 0)

    def test_cmd_add_from_outside_git(self):
        with ChdirTemporaryDirectory() as tmp_dname:
            root = Path("root")
            root.mkdir()
            os.chdir(str(root))

            make_repo()

            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            outside_file = Path(tmp_dname) / "outside.txt"
            outside_file.touch()

            # This should not be allowed!
            # It was blowing up with GitCommandError, per:
            # https://github.com/Aider-AI/aider/issues/178
            commands.cmd_add("../outside.txt")

            self.assertEqual(len(coder.abs_fnames), 0)

    def test_cmd_add_filename_with_special_chars(self):
        with ChdirTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            fname = Path("with[brackets].txt")
            fname.touch()

            commands.cmd_add(str(fname))

            self.assertIn(str(fname.resolve()), coder.abs_fnames)

    def test_cmd_tokens_output(self):
        with GitTemporaryDirectory() as repo_dir:
            # Create a small repository with a few files
            (Path(repo_dir) / "file1.txt").write_text("Content of file 1")
            (Path(repo_dir) / "file2.py").write_text("print('Content of file 2')")
            (Path(repo_dir) / "subdir").mkdir()
            (Path(repo_dir) / "subdir" / "file3.md").write_text("# Content of file 3")

            repo = git.Repo.init(repo_dir)
            repo.git.add(A=True)
            repo.git.commit("-m", "Initial commit")

            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(Model("claude-3-5-sonnet-20240620"), None, io)
            print(coder.get_announcements())
            commands = Commands(io, coder)

            commands.cmd_add("*.txt")

            # Capture the output of cmd_tokens
            original_tool_output = io.tool_output
            output_lines = []

            def capture_output(*args, **kwargs):
                output_lines.extend(args)
                original_tool_output(*args, **kwargs)

            io.tool_output = capture_output

            # Run cmd_tokens
            commands.cmd_tokens("")

            # Restore original tool_output
            io.tool_output = original_tool_output

            # Check if the output includes repository map information
            repo_map_line = next((line for line in output_lines if "repository map" in line), None)
            self.assertIsNotNone(
                repo_map_line, "Repository map information not found in the output"
            )

            # Check if the output includes information about all added files
            self.assertTrue(any("file1.txt" in line for line in output_lines))

            # Check if the total tokens and remaining tokens are reported
            self.assertTrue(any("tokens total" in line for line in output_lines))
            self.assertTrue(any("tokens remaining" in line for line in output_lines))

    def test_cmd_add_dirname_with_special_chars(self):
        with ChdirTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            dname = Path("with[brackets]")
            dname.mkdir()
            fname = dname / "filename.txt"
            fname.touch()

            commands.cmd_add(str(dname))

            dump(coder.abs_fnames)
            self.assertIn(str(fname.resolve()), coder.abs_fnames)

    def test_cmd_add_dirname_with_special_chars_git(self):
        with GitTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            dname = Path("with[brackets]")
            dname.mkdir()
            fname = dname / "filename.txt"
            fname.touch()

            repo = git.Repo()
            repo.git.add(str(fname))
            repo.git.commit("-m", "init")

            commands.cmd_add(str(dname))

            dump(coder.abs_fnames)
            self.assertIn(str(fname.resolve()), coder.abs_fnames)

    def test_cmd_add_abs_filename(self):
        with ChdirTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            fname = Path("file.txt")
            fname.touch()

            commands.cmd_add(str(fname.resolve()))

            self.assertIn(str(fname.resolve()), coder.abs_fnames)

    def test_cmd_add_quoted_filename(self):
        with ChdirTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            fname = Path("file with spaces.txt")
            fname.touch()

            commands.cmd_add(f'"{fname}"')

            self.assertIn(str(fname.resolve()), coder.abs_fnames)

    def test_cmd_add_existing_with_dirty_repo(self):
        with GitTemporaryDirectory():
            repo = git.Repo()

            files = ["one.txt", "two.txt"]
            for fname in files:
                Path(fname).touch()
                repo.git.add(fname)
            repo.git.commit("-m", "initial")

            commit = repo.head.commit.hexsha

            # leave a dirty `git rm`
            repo.git.rm("one.txt")

            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # There's no reason this /add should trigger a commit
            commands.cmd_add("two.txt")

            self.assertEqual(commit, repo.head.commit.hexsha)

            # Windows is throwing:
            # PermissionError: [WinError 32] The process cannot access
            # the file because it is being used by another process

            repo.git.commit("-m", "cleanup")

            del coder
            del commands
            del repo

    def test_cmd_save_and_load(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create some test files
            test_files = {
                "file1.txt": "Content of file 1",
                "file2.py": "print('Content of file 2')",
                "subdir/file3.md": "# Content of file 3",
            }

            for file_path, content in test_files.items():
                full_path = Path(repo_dir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # Add some files as editable and some as read-only
            commands.cmd_add("file1.txt file2.py")
            commands.cmd_read_only("subdir/file3.md")

            # Save the session to a file
            session_file = "test_session.txt"
            commands.cmd_save(session_file)

            # Verify the session file was created and contains the expected commands
            self.assertTrue(Path(session_file).exists())
            with open(session_file, encoding=io.encoding) as f:
                commands_text = f.read().splitlines()

                # Convert paths to absolute for comparison
                abs_file1 = str(Path("file1.txt").resolve())
                abs_file2 = str(Path("file2.py").resolve())
                abs_file3 = str(Path("subdir/file3.md").resolve())

                # Check each line for matching paths using os.path.samefile
                found_file1 = found_file2 = found_file3 = False
                for line in commands_text:
                    if line.startswith("/add "):
                        path = Path(line[5:].strip()).resolve()
                        if os.path.samefile(str(path), abs_file1):
                            found_file1 = True
                        elif os.path.samefile(str(path), abs_file2):
                            found_file2 = True
                    elif line.startswith("/read-only "):
                        path = Path(line[11:]).resolve()
                        if os.path.samefile(str(path), abs_file3):
                            found_file3 = True

                self.assertTrue(found_file1, "file1.txt not found in commands")
                self.assertTrue(found_file2, "file2.py not found in commands")
                self.assertTrue(found_file3, "file3.md not found in commands")

            # Clear the current session
            commands.cmd_reset("")
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

            # Load the session back
            commands.cmd_load(session_file)

            # Verify files were restored correctly
            added_files = {Path(coder.get_rel_fname(f)).as_posix() for f in coder.abs_fnames}
            read_only_files = {
                Path(coder.get_rel_fname(f)).as_posix() for f in coder.abs_read_only_fnames
            }

            self.assertEqual(added_files, {"file1.txt", "file2.py"})
            self.assertEqual(read_only_files, {"subdir/file3.md"})

            # Clean up
            Path(session_file).unlink()

    def test_cmd_save_and_load_with_external_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as external_file:
            external_file.write("External file content")
            external_file_path = external_file.name

        try:
            with GitTemporaryDirectory() as repo_dir:
                io = InputOutput(pretty=False, fancy_input=False, yes=True)
                coder = Coder.create(self.GPT35, None, io)
                commands = Commands(io, coder)

                # Create some test files in the repo
                test_files = {
                    "file1.txt": "Content of file 1",
                    "file2.py": "print('Content of file 2')",
                }

                for file_path, content in test_files.items():
                    full_path = Path(repo_dir) / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content)

                # Add some files as editable and some as read-only
                commands.cmd_add(str(Path("file1.txt")))
                commands.cmd_read_only(external_file_path)

                # Save the session to a file
                session_file = str(Path("test_session.txt"))
                commands.cmd_save(session_file)

                # Verify the session file was created and contains the expected commands
                self.assertTrue(Path(session_file).exists())
                with open(session_file, encoding=io.encoding) as f:
                    commands_text = f.read()
                    commands_text = re.sub(
                        r"/add +", "/add ", commands_text
                    )  # Normalize add command spaces
                    self.assertIn("/add file1.txt", commands_text)
                    # Split commands and check each one
                    for line in commands_text.splitlines():
                        if line.startswith("/read-only "):
                            saved_path = line.split(" ", 1)[1]
                            if os.path.samefile(saved_path, external_file_path):
                                break
                    else:
                        self.fail(f"No matching read-only command found for {external_file_path}")

                # Clear the current session
                commands.cmd_reset("")
                self.assertEqual(len(coder.abs_fnames), 0)
                self.assertEqual(len(coder.abs_read_only_fnames), 0)

                # Load the session back
                commands.cmd_load(session_file)

                # Verify files were restored correctly
                added_files = {coder.get_rel_fname(f) for f in coder.abs_fnames}
                read_only_files = {coder.get_rel_fname(f) for f in coder.abs_read_only_fnames}

                self.assertEqual(added_files, {str(Path("file1.txt"))})
                self.assertTrue(
                    any(os.path.samefile(external_file_path, f) for f in read_only_files)
                )

                # Clean up
                Path(session_file).unlink()

        finally:
            os.unlink(external_file_path)

    def test_cmd_save_and_load_with_multiple_external_files(self):
        with (
            tempfile.NamedTemporaryFile(mode="w", delete=False) as external_file1,
            tempfile.NamedTemporaryFile(mode="w", delete=False) as external_file2,
        ):
            external_file1.write("External file 1 content")
            external_file2.write("External file 2 content")
            external_file1_path = external_file1.name
            external_file2_path = external_file2.name

        try:
            with GitTemporaryDirectory() as repo_dir:
                io = InputOutput(pretty=False, fancy_input=False, yes=True)
                coder = Coder.create(self.GPT35, None, io)
                commands = Commands(io, coder)

                # Create some test files in the repo
                test_files = {
                    "internal1.txt": "Content of internal file 1",
                    "internal2.txt": "Content of internal file 2",
                }

                for file_path, content in test_files.items():
                    full_path = Path(repo_dir) / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content)

                # Add files as editable and read-only
                commands.cmd_add(str(Path("internal1.txt")))
                commands.cmd_read_only(external_file1_path)
                commands.cmd_read_only(external_file2_path)

                # Save the session to a file
                session_file = str(Path("test_session.txt"))
                commands.cmd_save(session_file)

                # Verify the session file was created and contains the expected commands
                self.assertTrue(Path(session_file).exists())
                with open(session_file, encoding=io.encoding) as f:
                    commands_text = f.read()
                    commands_text = re.sub(
                        r"/add +", "/add ", commands_text
                    )  # Normalize add command spaces
                    self.assertIn("/add internal1.txt", commands_text)
                    # Split commands and check each one
                    for line in commands_text.splitlines():
                        if line.startswith("/read-only "):
                            saved_path = line.split(" ", 1)[1]
                            if os.path.samefile(saved_path, external_file1_path):
                                break
                    else:
                        self.fail(f"No matching read-only command found for {external_file1_path}")
                    # Split commands and check each one
                    for line in commands_text.splitlines():
                        if line.startswith("/read-only "):
                            saved_path = line.split(" ", 1)[1]
                            if os.path.samefile(saved_path, external_file2_path):
                                break
                    else:
                        self.fail(f"No matching read-only command found for {external_file2_path}")

                # Clear the current session
                commands.cmd_reset("")
                self.assertEqual(len(coder.abs_fnames), 0)
                self.assertEqual(len(coder.abs_read_only_fnames), 0)

                # Load the session back
                commands.cmd_load(session_file)

                # Verify files were restored correctly
                added_files = {coder.get_rel_fname(f) for f in coder.abs_fnames}
                read_only_files = {coder.get_rel_fname(f) for f in coder.abs_read_only_fnames}

                self.assertEqual(added_files, {str(Path("internal1.txt"))})
                self.assertTrue(
                    all(
                        any(os.path.samefile(external_path, fname) for fname in read_only_files)
                        for external_path in [external_file1_path, external_file2_path]
                    )
                )

                # Clean up
                Path(session_file).unlink()

        finally:
            os.unlink(external_file1_path)
            os.unlink(external_file2_path)

    def test_cmd_read_only_with_image_file(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a test image file
            test_file = Path(repo_dir) / "test_image.jpg"
            test_file.write_text("Mock image content")

            # Test with non-vision model
            commands.cmd_read_only(str(test_file))
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

            # Test with vision model
            vision_model = Model("gpt-4-vision-preview")
            vision_coder = Coder.create(vision_model, None, io)
            vision_commands = Commands(io, vision_coder)

            vision_commands.cmd_read_only(str(test_file))
            self.assertEqual(len(vision_coder.abs_read_only_fnames), 1)
            self.assertTrue(
                any(
                    os.path.samefile(str(test_file), fname)
                    for fname in vision_coder.abs_read_only_fnames
                )
            )

            # Add a dummy message to ensure format_messages() works
            vision_coder.cur_messages = [{"role": "user", "content": "Check the image"}]

            # Check that the image file appears in the messages
            messages = vision_coder.format_messages().all_messages()
            found_image = False
            for msg in messages:
                if msg.get("role") == "user" and "content" in msg:
                    content = msg["content"]
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                if "test_image.jpg" in item.get("text", ""):
                                    found_image = True
                                    break
            self.assertTrue(found_image, "Image file not found in messages to LLM")

    def test_cmd_read_only_with_glob_pattern(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create multiple test files
            test_files = ["test_file1.txt", "test_file2.txt", "other_file.txt"]
            for file_name in test_files:
                file_path = Path(repo_dir) / file_name
                file_path.write_text(f"Content of {file_name}")

            # Test the /read-only command with a glob pattern
            commands.cmd_read_only("test_*.txt")

            # Check if only the matching files were added to abs_read_only_fnames
            self.assertEqual(len(coder.abs_read_only_fnames), 2)
            for file_name in ["test_file1.txt", "test_file2.txt"]:
                file_path = Path(repo_dir) / file_name
                self.assertTrue(
                    any(
                        os.path.samefile(str(file_path), fname)
                        for fname in coder.abs_read_only_fnames
                    )
                )

            # Check that other_file.txt was not added
            other_file_path = Path(repo_dir) / "other_file.txt"
            self.assertFalse(
                any(
                    os.path.samefile(str(other_file_path), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

    def test_cmd_read_only_with_recursive_glob(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a directory structure with files
            (Path(repo_dir) / "subdir").mkdir()
            test_files = ["test_file1.txt", "subdir/test_file2.txt", "subdir/other_file.txt"]
            for file_name in test_files:
                file_path = Path(repo_dir) / file_name
                file_path.write_text(f"Content of {file_name}")

            # Test the /read-only command with a recursive glob pattern
            commands.cmd_read_only("**/*.txt")

            # Check if all .txt files were added to abs_read_only_fnames
            self.assertEqual(len(coder.abs_read_only_fnames), 3)
            for file_name in test_files:
                file_path = Path(repo_dir) / file_name
                self.assertTrue(
                    any(
                        os.path.samefile(str(file_path), fname)
                        for fname in coder.abs_read_only_fnames
                    )
                )

    def test_cmd_read_only_with_nonexistent_glob(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Test the /read-only command with a non-existent glob pattern
            with mock.patch.object(io, "tool_error") as mock_tool_error:
                commands.cmd_read_only(str(Path(repo_dir) / "nonexistent*.txt"))

            # Check if the appropriate error message was displayed
            mock_tool_error.assert_called_once_with(
                f"No matches found for: {Path(repo_dir) / 'nonexistent*.txt'}"
            )

            # Ensure no files were added to abs_read_only_fnames
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

    def test_cmd_add_unicode_error(self):
        # Initialize the Commands and InputOutput objects
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        from aider.coders import Coder

        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        fname = "file.txt"
        encoding = "utf-16"
        some_content_which_will_error_if_read_with_encoding_utf8 = "ÅÍÎÏ".encode(encoding)
        with open(fname, "wb") as f:
            f.write(some_content_which_will_error_if_read_with_encoding_utf8)

        commands.cmd_add("file.txt")
        self.assertEqual(coder.abs_fnames, set())

    def test_cmd_add_read_only_file(self):
        with GitTemporaryDirectory():
            # Initialize the Commands and InputOutput objects
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a test file
            test_file = Path("test_read_only.txt")
            test_file.write_text("Test content")

            # Add the file as read-only
            commands.cmd_read_only(str(test_file))

            # Verify it's in abs_read_only_fnames
            self.assertTrue(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

            # Try to add the read-only file
            commands.cmd_add(str(test_file))

            # It's not in the repo, should not do anything
            self.assertFalse(
                any(os.path.samefile(str(test_file.resolve()), fname) for fname in coder.abs_fnames)
            )
            self.assertTrue(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

            repo = git.Repo()
            repo.git.add(str(test_file))
            repo.git.commit("-m", "initial")

            # Try to add the read-only file
            commands.cmd_add(str(test_file))

            # Verify it's now in abs_fnames and not in abs_read_only_fnames
            self.assertTrue(
                any(os.path.samefile(str(test_file.resolve()), fname) for fname in coder.abs_fnames)
            )
            self.assertFalse(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

    def test_cmd_test_unbound_local_error(self):
        with ChdirTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the io.prompt_ask method to simulate user input
            io.prompt_ask = lambda *args, **kwargs: "y"

            # Test the cmd_run method with a command that should not raise an error
            commands.cmd_run("exit 1", add_on_nonzero_exit=True)

            # Check that the output was added to cur_messages
            self.assertTrue(any("exit 1" in msg["content"] for msg in coder.cur_messages))

    def test_cmd_test_returns_output_on_failure(self):
        with ChdirTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Define a command that prints to stderr and exits with non-zero status
            test_cmd = "echo 'error output' >&2 && exit 1"
            expected_output_fragment = "error output"

            # Run cmd_test
            result = commands.cmd_test(test_cmd)

            # Assert that the result contains the expected output
            self.assertIsNotNone(result)
            self.assertIn(expected_output_fragment, result)
            # Check that the output was also added to cur_messages
            self.assertTrue(
                any(expected_output_fragment in msg["content"] for msg in coder.cur_messages)
            )

    def test_cmd_add_drop_untracked_files(self):
        with GitTemporaryDirectory():
            repo = git.Repo()

            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            from aider.coders import Coder

            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            fname = Path("test.txt")
            fname.touch()

            self.assertEqual(len(coder.abs_fnames), 0)

            commands.cmd_add(str(fname))

            files_in_repo = repo.git.ls_files()
            self.assertNotIn(str(fname), files_in_repo)

            self.assertEqual(len(coder.abs_fnames), 1)

            commands.cmd_drop(str(fname))

            self.assertEqual(len(coder.abs_fnames), 0)

    def test_cmd_undo_with_dirty_files_not_in_last_commit(self):
        with GitTemporaryDirectory() as repo_dir:
            repo = git.Repo(repo_dir)
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            other_path = Path(repo_dir) / "other_file.txt"
            other_path.write_text("other content")
            repo.git.add(str(other_path))

            # Create and commit a file
            filename = "test_file.txt"
            file_path = Path(repo_dir) / filename
            file_path.write_text("first content")
            repo.git.add(filename)
            repo.git.commit("-m", "first commit")

            file_path.write_text("second content")
            repo.git.add(filename)
            repo.git.commit("-m", "second commit")

            # Store the commit hash
            last_commit_hash = repo.head.commit.hexsha[:7]
            coder.aider_commit_hashes.add(last_commit_hash)

            file_path.write_text("dirty content")

            # Attempt to undo the last commit
            commands.cmd_undo("")

            # Check that the last commit is still present
            self.assertEqual(last_commit_hash, repo.head.commit.hexsha[:7])

            # Put back the initial content (so it's not dirty now)
            file_path.write_text("second content")
            other_path.write_text("dirty content")

            commands.cmd_undo("")
            self.assertNotEqual(last_commit_hash, repo.head.commit.hexsha[:7])

            self.assertEqual(file_path.read_text(), "first content")
            self.assertEqual(other_path.read_text(), "dirty content")

            del coder
            del commands
            del repo

    def test_cmd_undo_with_newly_committed_file(self):
        with GitTemporaryDirectory() as repo_dir:
            repo = git.Repo(repo_dir)
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Put in a random first commit
            filename = "first_file.txt"
            file_path = Path(repo_dir) / filename
            file_path.write_text("new file content")
            repo.git.add(filename)
            repo.git.commit("-m", "Add new file")

            # Create and commit a new file
            filename = "new_file.txt"
            file_path = Path(repo_dir) / filename
            file_path.write_text("new file content")
            repo.git.add(filename)
            repo.git.commit("-m", "Add new file")

            # Store the commit hash
            last_commit_hash = repo.head.commit.hexsha[:7]
            coder.aider_commit_hashes.add(last_commit_hash)

            # Attempt to undo the last commit, should refuse
            commands.cmd_undo("")

            # Check that the last commit was not undone
            self.assertEqual(last_commit_hash, repo.head.commit.hexsha[:7])
            self.assertTrue(file_path.exists())

            del coder
            del commands
            del repo

    def test_cmd_undo_on_first_commit(self):
        with GitTemporaryDirectory() as repo_dir:
            repo = git.Repo(repo_dir)
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create and commit a new file
            filename = "new_file.txt"
            file_path = Path(repo_dir) / filename
            file_path.write_text("new file content")
            repo.git.add(filename)
            repo.git.commit("-m", "Add new file")

            # Store the commit hash
            last_commit_hash = repo.head.commit.hexsha[:7]
            coder.aider_commit_hashes.add(last_commit_hash)

            # Attempt to undo the last commit
            commands.cmd_undo("")

            # Check that the commit is still present
            self.assertEqual(last_commit_hash, repo.head.commit.hexsha[:7])
            self.assertTrue(file_path.exists())

            del coder
            del commands
            del repo

    def test_cmd_add_gitignored_file(self):
        with GitTemporaryDirectory():
            # Create a .gitignore file
            gitignore = Path(".gitignore")
            gitignore.write_text("*.ignored\n")

            # Create a file that matches the gitignore pattern
            ignored_file = Path("test.ignored")
            ignored_file.write_text("This should be ignored")

            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Try to add the ignored file
            commands.cmd_add(str(ignored_file))

            # Verify the file was not added
            self.assertEqual(len(coder.abs_fnames), 0)

    def test_cmd_think_tokens(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with various formats
        test_values = {
            "8k": 8192,  # 8 * 1024
            "10.5k": 10752,  # 10.5 * 1024
            "512k": 524288,  # 0.5 * 1024 * 1024
        }

        for input_value, expected_tokens in test_values.items():
            with mock.patch.object(io, "tool_output") as mock_tool_output:
                commands.cmd_think_tokens(input_value)

                # Check that the model's thinking tokens were updated
                self.assertEqual(
                    coder.main_model.extra_params["thinking"]["budget_tokens"], expected_tokens
                )

                # Check that the tool output shows the correct value with format
                # Use the actual input_value (not normalized) in the assertion
                mock_tool_output.assert_any_call(
                    f"Set thinking token budget to {expected_tokens:,} tokens ({input_value})."
                )

        # Test with no value provided - should display current value
        with mock.patch.object(io, "tool_output") as mock_tool_output:
            commands.cmd_think_tokens("")
            mock_tool_output.assert_any_call(mock.ANY)  # Just verify it calls tool_output

    def test_cmd_add_aiderignored_file(self):
        with GitTemporaryDirectory():
            repo = git.Repo()

            fname1 = "ignoreme1.txt"
            fname2 = "ignoreme2.txt"
            fname3 = "dir/ignoreme3.txt"

            Path(fname2).touch()
            repo.git.add(str(fname2))
            repo.git.commit("-m", "initial")

            aignore = Path(".aiderignore")
            aignore.write_text(f"{fname1}\n{fname2}\ndir\n")

            io = InputOutput(yes=True)

            fnames = [fname1, fname2]
            repo = GitRepo(
                io,
                fnames,
                None,
                aider_ignore_file=str(aignore),
            )

            coder = Coder.create(
                self.GPT35,
                None,
                io,
                fnames=fnames,
                repo=repo,
            )
            commands = Commands(io, coder)

            commands.cmd_add(f"{fname1} {fname2} {fname3}")

            self.assertNotIn(fname1, str(coder.abs_fnames))
            self.assertNotIn(fname2, str(coder.abs_fnames))
            self.assertNotIn(fname3, str(coder.abs_fnames))

    def test_cmd_read_only(self):
        with GitTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a test file
            test_file = Path("test_read.txt")
            test_file.write_text("Test content")

            # Test the /read command
            commands.cmd_read_only(str(test_file))

            # Check if the file was added to abs_read_only_fnames
            self.assertTrue(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

            # Test dropping the read-only file
            commands.cmd_drop(str(test_file))

            # Check if the file was removed from abs_read_only_fnames
            self.assertFalse(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

    def test_cmd_read_only_from_working_dir(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a subdirectory and a test file within it
            subdir = Path(repo_dir) / "subdir"
            subdir.mkdir()
            test_file = subdir / "test_read_only_file.txt"
            test_file.write_text("Test content")

            # Change the current working directory to the subdirectory
            os.chdir(subdir)

            # Test the /read-only command using git_root referenced name
            commands.cmd_read_only(os.path.join("subdir", "test_read_only_file.txt"))

            # Check if the file was added to abs_read_only_fnames
            self.assertTrue(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

            # Test dropping the read-only file using git_root referenced name
            commands.cmd_drop(os.path.join("subdir", "test_read_only_file.txt"))

            # Check if the file was removed from abs_read_only_fnames
            self.assertFalse(
                any(
                    os.path.samefile(str(test_file.resolve()), fname)
                    for fname in coder.abs_read_only_fnames
                )
            )

    def test_cmd_read_only_with_external_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as external_file:
            external_file.write("External file content")
            external_file_path = external_file.name

        try:
            with GitTemporaryDirectory() as repo_dir:
                # Create a test file in the repo
                repo_file = Path(repo_dir) / "repo_file.txt"
                repo_file.write_text("Repo file content")
                io = InputOutput(pretty=False, fancy_input=False, yes=False)
                coder = Coder.create(self.GPT35, None, io)
                commands = Commands(io, coder)

                # Test the /read command with an external file
                commands.cmd_read_only(external_file_path)

                # Check if the external file was added to abs_read_only_fnames
                real_external_file_path = os.path.realpath(external_file_path)
                self.assertTrue(
                    any(
                        os.path.samefile(real_external_file_path, fname)
                        for fname in coder.abs_read_only_fnames
                    )
                )

                # Test dropping the external read-only file
                commands.cmd_drop(Path(external_file_path).name)

                # Check if the file was removed from abs_read_only_fnames
                self.assertFalse(
                    any(
                        os.path.samefile(real_external_file_path, fname)
                        for fname in coder.abs_read_only_fnames
                    )
                )
        finally:
            os.unlink(external_file_path)

    def test_cmd_drop_read_only_with_relative_path(self):
        with ChdirTemporaryDirectory() as repo_dir:
            test_file = Path("test_file.txt")
            test_file.write_text("Test content")

            # Create a test file in a subdirectory
            subdir = Path(repo_dir) / "subdir"
            subdir.mkdir()
            os.chdir(subdir)

            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Add the file as read-only using absolute path
            rel_path = str(Path("..") / "test_file.txt")
            commands.cmd_read_only(rel_path)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)

            # Try to drop using relative path from different working directories
            commands.cmd_drop("test_file.txt")
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

            # Add it again
            commands.cmd_read_only(rel_path)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)

            commands.cmd_drop(rel_path)
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

            # Add it one more time
            commands.cmd_read_only(rel_path)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)

            commands.cmd_drop("test_file.txt")
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

    def test_cmd_read_only_bulk_conversion(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create and add some test files
            test_files = ["test1.txt", "test2.txt", "test3.txt"]
            for fname in test_files:
                Path(fname).write_text(f"Content of {fname}")
                commands.cmd_add(fname)

            # Verify files are in editable mode
            self.assertEqual(len(coder.abs_fnames), 3)
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

            # Convert all files to read-only mode
            commands.cmd_read_only("")

            # Verify all files were moved to read-only
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 3)

            # Check specific files
            for fname in test_files:
                abs_path = Path(repo_dir) / fname
                self.assertTrue(
                    any(
                        os.path.samefile(str(abs_path), ro_fname)
                        for ro_fname in coder.abs_read_only_fnames
                    )
                )

    def test_cmd_read_only_with_multiple_files(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create multiple test files
            test_files = ["test_file1.txt", "test_file2.txt", "test_file3.txt"]
            for file_name in test_files:
                file_path = Path(repo_dir) / file_name
                file_path.write_text(f"Content of {file_name}")

            # Test the /read-only command with multiple files
            commands.cmd_read_only(" ".join(test_files))

            # Check if all test files were added to abs_read_only_fnames
            for file_name in test_files:
                file_path = Path(repo_dir) / file_name
                self.assertTrue(
                    any(
                        os.path.samefile(str(file_path), fname)
                        for fname in coder.abs_read_only_fnames
                    )
                )

            # Test dropping all read-only files
            commands.cmd_drop(" ".join(test_files))

            # Check if all files were removed from abs_read_only_fnames
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

    def test_cmd_read_only_with_tilde_path(self):
        with GitTemporaryDirectory():
            io = InputOutput(pretty=False, fancy_input=False, yes=False)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a test file in the user's home directory
            home_dir = os.path.expanduser("~")
            test_file = Path(home_dir) / "test_read_only_file.txt"
            test_file.write_text("Test content")

            try:
                # Test the /read-only command with a path in the user's home directory
                relative_path = os.path.join("~", "test_read_only_file.txt")
                commands.cmd_read_only(relative_path)

                # Check if the file was added to abs_read_only_fnames
                self.assertTrue(
                    any(
                        os.path.samefile(str(test_file), fname)
                        for fname in coder.abs_read_only_fnames
                    )
                )

                # Test dropping the read-only file
                commands.cmd_drop(relative_path)

                # Check if the file was removed from abs_read_only_fnames
                self.assertEqual(len(coder.abs_read_only_fnames), 0)

            finally:
                # Clean up: remove the test file from the home directory
                test_file.unlink()

    def test_cmd_diff(self):
        with GitTemporaryDirectory() as repo_dir:
            repo = git.Repo(repo_dir)
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create and commit a file
            filename = "test_file.txt"
            file_path = Path(repo_dir) / filename
            file_path.write_text("Initial content\n")
            repo.git.add(filename)
            repo.git.commit("-m", "Initial commit\n")

            # Modify the file to make it dirty
            file_path.write_text("Modified content")

            # Mock repo.get_commit_message to return a canned commit message
            with mock.patch.object(
                coder.repo, "get_commit_message", return_value="Canned commit message"
            ):
                # Run cmd_commit
                commands.cmd_commit()

                # Capture the output of cmd_diff
                with mock.patch("builtins.print") as mock_print:
                    commands.cmd_diff("")

                # Check if the diff output is correct
                mock_print.assert_called_with(mock.ANY)
                diff_output = mock_print.call_args[0][0]
                self.assertIn("-Initial content", diff_output)
                self.assertIn("+Modified content", diff_output)

                # Modify the file again
                file_path.write_text("Further modified content")

                # Run cmd_commit again
                commands.cmd_commit()

                # Capture the output of cmd_diff
                with mock.patch("builtins.print") as mock_print:
                    commands.cmd_diff("")

                # Check if the diff output is correct
                mock_print.assert_called_with(mock.ANY)
                diff_output = mock_print.call_args[0][0]
                self.assertIn("-Modified content", diff_output)
                self.assertIn("+Further modified content", diff_output)

                # Modify the file a third time
                file_path.write_text("Final modified content")

                # Run cmd_commit again
                commands.cmd_commit()

                # Capture the output of cmd_diff
                with mock.patch("builtins.print") as mock_print:
                    commands.cmd_diff("")

                # Check if the diff output is correct
                mock_print.assert_called_with(mock.ANY)
                diff_output = mock_print.call_args[0][0]
                self.assertIn("-Further modified content", diff_output)
                self.assertIn("+Final modified content", diff_output)

    def test_cmd_model(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test switching the main model
        with self.assertRaises(SwitchCoder) as context:
            commands.cmd_model("gpt-4")

        # Check that the SwitchCoder exception contains the correct model configuration
        self.assertEqual(context.exception.kwargs.get("main_model").name, "gpt-4")
        self.assertEqual(
            context.exception.kwargs.get("main_model").editor_model.name,
            self.GPT35.editor_model.name,
        )
        self.assertEqual(
            context.exception.kwargs.get("main_model").weak_model.name, self.GPT35.weak_model.name
        )
        # Check that the edit format is updated to the new model's default
        self.assertEqual(context.exception.kwargs.get("edit_format"), "diff")

    def test_cmd_model_preserves_explicit_edit_format(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        # Use gpt-3.5-turbo (default 'diff')
        coder = Coder.create(self.GPT35, None, io)
        # Explicitly set edit format to something else
        coder.edit_format = "udiff"
        commands = Commands(io, coder)

        # Mock sanity check to avoid network calls
        with mock.patch("aider.models.sanity_check_models"):
            # Test switching the main model to gpt-4 (default 'whole')
            with self.assertRaises(SwitchCoder) as context:
                commands.cmd_model("gpt-4")

        # Check that the SwitchCoder exception contains the correct model configuration
        self.assertEqual(context.exception.kwargs.get("main_model").name, "gpt-4")
        # Check that the edit format is preserved
        self.assertEqual(context.exception.kwargs.get("edit_format"), "udiff")

    def test_cmd_editor_model(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test switching the editor model
        with self.assertRaises(SwitchCoder) as context:
            commands.cmd_editor_model("gpt-4")

        # Check that the SwitchCoder exception contains the correct model configuration
        self.assertEqual(context.exception.kwargs.get("main_model").name, self.GPT35.name)
        self.assertEqual(context.exception.kwargs.get("main_model").editor_model.name, "gpt-4")
        self.assertEqual(
            context.exception.kwargs.get("main_model").weak_model.name, self.GPT35.weak_model.name
        )

    def test_cmd_weak_model(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test switching the weak model
        with self.assertRaises(SwitchCoder) as context:
            commands.cmd_weak_model("gpt-4")

        # Check that the SwitchCoder exception contains the correct model configuration
        self.assertEqual(context.exception.kwargs.get("main_model").name, self.GPT35.name)
        self.assertEqual(
            context.exception.kwargs.get("main_model").editor_model.name,
            self.GPT35.editor_model.name,
        )
        self.assertEqual(context.exception.kwargs.get("main_model").weak_model.name, "gpt-4")

    def test_cmd_model_updates_default_edit_format(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        # Use gpt-3.5-turbo (default 'diff')
        coder = Coder.create(self.GPT35, None, io)
        # Ensure current edit format is the default
        self.assertEqual(coder.edit_format, self.GPT35.edit_format)
        commands = Commands(io, coder)

        # Mock sanity check to avoid network calls
        with mock.patch("aider.models.sanity_check_models"):
            # Test switching the main model to gpt-4 (default 'whole')
            with self.assertRaises(SwitchCoder) as context:
                commands.cmd_model("gpt-4")

        # Check that the SwitchCoder exception contains the correct model configuration
        self.assertEqual(context.exception.kwargs.get("main_model").name, "gpt-4")
        # Check that the edit format is updated to the new model's default
        self.assertEqual(context.exception.kwargs.get("edit_format"), "diff")

    def test_cmd_ask(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        question = "What is the meaning of life?"
        canned_reply = "The meaning of life is 42."

        with mock.patch("aider.coders.Coder.run") as mock_run:
            mock_run.return_value = canned_reply

            with self.assertRaises(SwitchCoder):
                commands.cmd_ask(question)

            mock_run.assert_called_once()
            mock_run.assert_called_once_with(question)

    def test_cmd_lint_with_dirty_file(self):
        with GitTemporaryDirectory() as repo_dir:
            repo = git.Repo(repo_dir)
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create and commit a file
            filename = "test_file.py"
            file_path = Path(repo_dir) / filename
            file_path.write_text("def hello():\n    print('Hello, World!')\n")
            repo.git.add(filename)
            repo.git.commit("-m", "Add test_file.py")

            # Modify the file to make it dirty
            file_path.write_text("def hello():\n    print('Hello, World!')\n\n# Dirty line\n")

            # Mock the linter.lint method
            with mock.patch.object(coder.linter, "lint") as mock_lint:
                # Set up the mock to return an empty string (no lint errors)
                mock_lint.return_value = ""

                # Run cmd_lint
                commands.cmd_lint()

                # Check if the linter was called with a filename string
                # whose Path().name matches the expected filename
                mock_lint.assert_called_once()
                called_arg = mock_lint.call_args[0][0]
                self.assertEqual(Path(called_arg).name, filename)

            # Verify that the file is still dirty after linting
            self.assertTrue(repo.is_dirty(filename))

            del coder
            del commands
            del repo

    def test_cmd_reset(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Add some files to the chat
            file1 = Path(repo_dir) / "file1.txt"
            file2 = Path(repo_dir) / "file2.txt"
            file1.write_text("Content of file 1")
            file2.write_text("Content of file 2")
            commands.cmd_add(f"{file1} {file2}")

            # Add some messages to the chat history
            coder.cur_messages = [{"role": "user", "content": "Test message 1"}]
            coder.done_messages = [{"role": "assistant", "content": "Test message 2"}]

            # Run the reset command
            commands.cmd_reset("")

            # Check that all files have been dropped
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

            # Check that the chat history has been cleared
            self.assertEqual(len(coder.cur_messages), 0)
            self.assertEqual(len(coder.done_messages), 0)

            # Verify that the files still exist in the repository
            self.assertTrue(file1.exists())
            self.assertTrue(file2.exists())

            del coder
            del commands

    def test_reset_with_original_read_only_files(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)

            # Create test files
            orig_read_only = Path(repo_dir) / "orig_read_only.txt"
            orig_read_only.write_text("Original read-only file")

            added_file = Path(repo_dir) / "added_file.txt"
            added_file.write_text("Added file")

            added_read_only = Path(repo_dir) / "added_read_only.txt"
            added_read_only.write_text("Added read-only file")

            # Initialize commands with original read-only files
            commands = Commands(io, coder, original_read_only_fnames=[str(orig_read_only)])

            # Add files to the chat
            coder.abs_read_only_fnames.add(str(orig_read_only))
            coder.abs_fnames.add(str(added_file))
            coder.abs_read_only_fnames.add(str(added_read_only))

            # Add some messages to the chat history
            coder.cur_messages = [{"role": "user", "content": "Test message"}]
            coder.done_messages = [{"role": "assistant", "content": "Test response"}]

            # Verify initial state
            self.assertEqual(len(coder.abs_fnames), 1)
            self.assertEqual(len(coder.abs_read_only_fnames), 2)
            self.assertEqual(len(coder.cur_messages), 1)
            self.assertEqual(len(coder.done_messages), 1)

            # Test reset command
            commands.cmd_reset("")

            # Verify that original read-only file is preserved
            # but other files and messages are cleared
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)
            self.assertIn(str(orig_read_only), coder.abs_read_only_fnames)
            self.assertNotIn(str(added_read_only), coder.abs_read_only_fnames)

            # Chat history should be cleared
            self.assertEqual(len(coder.cur_messages), 0)
            self.assertEqual(len(coder.done_messages), 0)

    def test_reset_with_no_original_read_only_files(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)

            # Create test files
            added_file = Path(repo_dir) / "added_file.txt"
            added_file.write_text("Added file")

            added_read_only = Path(repo_dir) / "added_read_only.txt"
            added_read_only.write_text("Added read-only file")

            # Initialize commands with no original read-only files
            commands = Commands(io, coder)

            # Add files to the chat
            coder.abs_fnames.add(str(added_file))
            coder.abs_read_only_fnames.add(str(added_read_only))

            # Add some messages to the chat history
            coder.cur_messages = [{"role": "user", "content": "Test message"}]
            coder.done_messages = [{"role": "assistant", "content": "Test response"}]

            # Verify initial state
            self.assertEqual(len(coder.abs_fnames), 1)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)
            self.assertEqual(len(coder.cur_messages), 1)
            self.assertEqual(len(coder.done_messages), 1)

            # Test reset command
            commands.cmd_reset("")

            # Verify that all files and messages are cleared
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 0)
            self.assertEqual(len(coder.cur_messages), 0)
            self.assertEqual(len(coder.done_messages), 0)

    def test_cmd_code_from_plan_positive(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a test plan file
            plan_file = Path(repo_dir) / "test_plan.md"
            plan_content = """# Test Plan
## Step 1
- Create a function that adds two numbers
## Step 2
- Create a function that multiplies two numbers
"""
            plan_file.write_text(plan_content)
            # Mock the necessary methods
            with (
                mock.patch.object(commands, "_run_new_coder") as mock_run_new_coder,
                mock.patch.object(
                    commands, "_from_plan_exist_strategy"
                ) as mock_from_plan_exist_strategy,
                mock.patch.object(io, "tool_output") as mock_tool_output,
            ):
                # Mock the coder.run method to return a step count
                mock_run_instance = mock.MagicMock()
                mock_run_instance.run.return_value = "2"

                with mock.patch(
                    "aider.coders.base_coder.Coder.create", return_value=mock_run_instance
                ):
                    # Execute the command
                    commands.cmd_code_from_plan(str(plan_file))

                    # Verify that the plan file was added to the chat
                    mock_run_instance.run.assert_called_once()

                    # Verify that _run_new_coder was called twice (once for each step)
                    self.assertEqual(mock_run_new_coder.call_count, 2)

                    # Verify the arguments for the first call to _run_new_coder
                    first_call_args = mock_run_new_coder.call_args_list[0][0]
                    self.assertIn("step 1", first_call_args[0].lower())
                    self.assertEqual(first_call_args[1], ["test_plan.md"])
                    self.assertFalse(first_call_args[2])

                    # Verify the arguments for the second call to _run_new_coder
                    second_call_args = mock_run_new_coder.call_args_list[1][0]
                    self.assertIn("step 2", second_call_args[0].lower())
                    self.assertEqual(second_call_args[1], ["test_plan.md"])
                    self.assertFalse(second_call_args[2])

                    # Verify that _from_plan_exist_strategy was called once
                    mock_from_plan_exist_strategy.assert_called_once()

                    # Verify that tool_output was called with the expected messages
                    mock_tool_output.assert_any_call("Found 2 steps in the plan.")
                    mock_tool_output.assert_any_call("Implementing step 1")
                    mock_tool_output.assert_any_call("Implementing step 2")

    def test_cmd_code_from_plan_error_handling(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Test case 1: File not found
            with mock.patch.object(io, "tool_error") as mock_tool_error:
                # Execute the command with a non-existent file
                commands.cmd_code_from_plan("non_existent_file.md")

                # Verify that tool_error was called with the expected message
                mock_tool_error.assert_called_once()
                self.assertIn("Plan file not found", mock_tool_error.call_args[0][0])

            # Test case 2: File exists but is not a valid plan
            invalid_plan_file = Path(repo_dir) / "invalid_plan.md"
            invalid_plan_file.write_text("This is not a valid plan file.")

            with mock.patch.object(io, "tool_error") as mock_tool_error:
                # Mock the coder.run method to raise ValueError
                mock_run_instance = mock.MagicMock()
                mock_run_instance.run.side_effect = ValueError(
                    "Could not determine the number of steps"
                )

                with mock.patch(
                    "aider.coders.base_coder.Coder.create", return_value=mock_run_instance
                ):
                    # Execute the command with an invalid plan file and expect ValueError
                    with self.assertRaises(ValueError):
                        commands.cmd_code_from_plan(str(invalid_plan_file))

    def test_completions_raw_code_from_plan_positive(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create test files for completion
            plan_file = Path(repo_dir) / "test_plan.md"
            plan_file.write_text("# Test Plan\n\n## Step 1\n- Create a function\n")

            # Create a document with partial command text
            document = Document("/code-from-plan test", cursor_position=16)

            # Create a mock completion event
            complete_event = mock.MagicMock()

            # Test the completions_raw_code_from_plan method
            with mock.patch.object(commands, "completions_raw_read_only") as mock_completions:
                # Set up the mock to return some completions
                mock_completions.return_value = [
                    Completion(text="test_plan.md", start_position=-4, display="test_plan.md")
                ]

                # Call the method
                completions = list(
                    commands.completions_raw_code_from_plan(document, complete_event)
                )

                # Verify that completions_raw_read_only was called with the correct arguments
                mock_completions.assert_called_once()
                self.assertEqual(mock_completions.call_args[0][0], document)
                self.assertEqual(mock_completions.call_args[0][1], complete_event)

                # Verify that the completions were returned correctly
                self.assertEqual(len(completions), 1)
                self.assertEqual(completions[0].text, "test_plan.md")
                self.assertEqual(completions[0].start_position, -4)

            # Test with different document text
            document2 = Document("/code-from-plan ", cursor_position=15)

            with mock.patch.object(commands, "completions_raw_read_only") as mock_completions:
                # Set up the mock to return some completions
                mock_completions.return_value = [
                    Completion(text="test_plan.md", start_position=0, display="test_plan.md")
                ]

                # Call the method
                completions = list(
                    commands.completions_raw_code_from_plan(document2, complete_event)
                )

                # Verify that completions_raw_read_only was called with the correct arguments
                mock_completions.assert_called_once()
                self.assertEqual(mock_completions.call_args[0][0], document2)
                self.assertEqual(mock_completions.call_args[0][1], complete_event)

                # Verify that the completions were returned correctly
                self.assertEqual(len(completions), 1)
                self.assertEqual(completions[0].text, "test_plan.md")
                self.assertEqual(completions[0].start_position, 0)

    def test_completions_raw_code_from_plan_error_handling(self):
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Test case 1: Invalid command format (no space after command)
            document1 = Document("/code-from-plan", cursor_position=15)
            complete_event = mock.MagicMock()

            # The function should return an empty list when the command format is invalid
            completions = list(commands.completions_raw_code_from_plan(document1, complete_event))
            self.assertEqual(len(completions), 0)

            # Test case 2: completions_raw_read_only returns empty list
            document2 = Document("/code-from-plan ", cursor_position=16)

            with mock.patch.object(
                commands, "completions_raw_read_only", return_value=[]
            ) as mock_completions:
                completions = list(
                    commands.completions_raw_code_from_plan(document2, complete_event)
                )

                # Verify that completions_raw_read_only was called
                mock_completions.assert_called_once()

                # Verify that an empty list is returned
                self.assertEqual(len(completions), 0)

    def test_run_new_coder(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create test files
            test_file = Path(repo_dir) / "test_file.py"
            test_file.write_text("def hello():\n    return 'Hello, World!'\n")

            # Add the file to the chat
            commands.cmd_add(str(test_file))

            # Set up mocks
            with (
                mock.patch("aider.coders.base_coder.Coder.create") as mock_create,
                mock.patch.object(io, "tool_output") as mock_tool_output,
                mock.patch.object(commands, "cmd_drop") as mock_cmd_drop,
            ):
                # Create a mock coder instance
                mock_coder = mock.MagicMock()
                mock_coder.get_inchat_relative_files.return_value = ["test_file.py", "new_file.py"]
                mock_create.return_value = mock_coder

                # Test _run_new_coder with basic parameters
                prompt = "Implement a new function"
                exclude_from_drop = ["test_file.py"]
                summarize_from_coder = True

                # Call the method
                commands._run_new_coder(prompt, exclude_from_drop, summarize_from_coder)

                # Verify Coder.create was called with correct parameters
                mock_create.assert_called_once()
                create_args = mock_create.call_args
                self.assertEqual(create_args[1]["io"], io)
                self.assertEqual(create_args[1]["from_coder"], coder)
                self.assertEqual(create_args[1]["edit_format"], coder.main_model.edit_format)
                self.assertEqual(create_args[1]["summarize_from_coder"], summarize_from_coder)

                # Verify the coder.run was called with the prompt
                mock_coder.run.assert_called_once_with(prompt)

                # Verify that cmd_drop was called with the correct files
                # (files in chat minus excluded files)
                mock_cmd_drop.assert_called_once_with("new_file.py")

                # Verify that tool_output was called to inform about dropped files
                mock_tool_output.assert_any_call("Dropping files in chat: ['new_file.py']")

                # Verify that the coder instance was updated
                self.assertEqual(commands.coder, mock_coder)

    def test_run_new_coder_with_exception(self):
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Set up mocks
            with (
                mock.patch("aider.coders.base_coder.Coder.create") as mock_create,
                mock.patch.object(commands, "cmd_drop") as mock_cmd_drop,
            ):
                # Create a mock coder instance that raises an exception during run
                mock_coder = mock.MagicMock()
                mock_coder.run.side_effect = Exception("Test exception")
                mock_create.return_value = mock_coder

                # Test _run_new_coder with an exception during run
                prompt = "Implement a new function"
                exclude_from_drop = []
                summarize_from_coder = False

                # Call the method - it should handle the exception
                with self.assertRaises(Exception) as context:
                    commands._run_new_coder(prompt, exclude_from_drop, summarize_from_coder)

                # Verify the exception was raised
                self.assertEqual(str(context.exception), "Test exception")

                # Verify Coder.create was called
                mock_create.assert_called_once()

                # Verify the coder.run was called with the prompt
                mock_coder.run.assert_called_once_with(prompt)

                # Verify that cmd_drop was not called since an exception occurred
                mock_cmd_drop.assert_not_called()

    def test_from_plan_exist_strategy(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a test file
            test_file = Path(repo_dir) / "test_file.py"
            test_file.write_text("def hello():\n    return 'Hello, World!'\n")

            # Add the file to the chat
            commands.cmd_add(str(test_file))

            # Create a mock for the original_confirmation_ask_method
            original_confirm_ask = mock.MagicMock()

            # Mock tool_output to verify completion message
            with mock.patch.object(io, "tool_output") as mock_tool_output:
                # Test that SwitchCoder is raised with the correct parameters
                with self.assertRaises(SwitchCoder) as context:
                    commands._from_plan_exist_strategy(original_confirm_ask)

                # Verify that the completion message was shown
                mock_tool_output.assert_called_with("\nPlan execution completed!")

                # Verify that the io.confirm_ask was restored to the original method
                self.assertEqual(io.confirm_ask, original_confirm_ask)

                # Verify the SwitchCoder exception contains the correct parameters
                exception = context.exception
                self.assertEqual(exception.kwargs.get("edit_format"), coder.edit_format)
                self.assertEqual(exception.kwargs.get("summarize_from_coder"), False)
                self.assertEqual(exception.kwargs.get("from_coder"), coder)
                self.assertEqual(exception.kwargs.get("show_announcements"), False)
                self.assertIsNone(exception.kwargs.get("placeholder"))

    def test_cmd_reasoning_effort(self):
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with numeric values
        with mock.patch.object(io, "tool_output") as mock_tool_output:
            commands.cmd_reasoning_effort("0.8")
            mock_tool_output.assert_any_call("Set reasoning effort to 0.8")

        # Test with text values (low/medium/high)
        for effort_level in ["low", "medium", "high"]:
            with mock.patch.object(io, "tool_output") as mock_tool_output:
                commands.cmd_reasoning_effort(effort_level)
                mock_tool_output.assert_any_call(f"Set reasoning effort to {effort_level}")

        # Check model's reasoning effort was updated
        with mock.patch.object(coder.main_model, "set_reasoning_effort") as mock_set_effort:
            commands.cmd_reasoning_effort("0.5")
            mock_set_effort.assert_called_once_with("0.5")

        # Test with no value provided - should display current value
        with mock.patch.object(io, "tool_output") as mock_tool_output:
            commands.cmd_reasoning_effort("")
            mock_tool_output.assert_any_call("Current reasoning effort: high")

    def test_drop_with_original_read_only_files(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)

            # Create test files
            orig_read_only = Path(repo_dir) / "orig_read_only.txt"
            orig_read_only.write_text("Original read-only file")

            added_file = Path(repo_dir) / "added_file.txt"
            added_file.write_text("Added file")

            added_read_only = Path(repo_dir) / "added_read_only.txt"
            added_read_only.write_text("Added read-only file")

            # Initialize commands with original read-only files
            commands = Commands(io, coder, original_read_only_fnames=[str(orig_read_only)])

            # Add files to the chat
            coder.abs_read_only_fnames.add(str(orig_read_only))
            coder.abs_fnames.add(str(added_file))
            coder.abs_read_only_fnames.add(str(added_read_only))

            # Verify initial state
            self.assertEqual(len(coder.abs_fnames), 1)
            self.assertEqual(len(coder.abs_read_only_fnames), 2)

            # Test bare drop command
            with mock.patch.object(io, "tool_output") as mock_tool_output:
                commands.cmd_drop("")
                mock_tool_output.assert_called_with(
                    "Dropping all files from the chat session except originally read-only files."
                )

            # Verify that original read-only file is preserved, but other files are dropped
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)
            self.assertIn(str(orig_read_only), coder.abs_read_only_fnames)
            self.assertNotIn(str(added_read_only), coder.abs_read_only_fnames)

    def test_drop_specific_original_read_only_file(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)

            # Create test file
            orig_read_only = Path(repo_dir) / "orig_read_only.txt"
            orig_read_only.write_text("Original read-only file")

            # Initialize commands with original read-only files
            commands = Commands(io, coder, original_read_only_fnames=[str(orig_read_only)])

            # Add file to the chat
            coder.abs_read_only_fnames.add(str(orig_read_only))

            # Verify initial state
            self.assertEqual(len(coder.abs_read_only_fnames), 1)

            # Test specific drop command
            commands.cmd_drop("orig_read_only.txt")

            # Verify that the original read-only file is dropped when specified explicitly
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

    def test_drop_with_no_original_read_only_files(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)

            # Create test files
            added_file = Path(repo_dir) / "added_file.txt"
            added_file.write_text("Added file")

            added_read_only = Path(repo_dir) / "added_read_only.txt"
            added_read_only.write_text("Added read-only file")

            # Initialize commands with no original read-only files
            commands = Commands(io, coder)

            # Add files to the chat
            coder.abs_fnames.add(str(added_file))
            coder.abs_read_only_fnames.add(str(added_read_only))

            # Verify initial state
            self.assertEqual(len(coder.abs_fnames), 1)
            self.assertEqual(len(coder.abs_read_only_fnames), 1)

            # Test bare drop command
            with mock.patch.object(io, "tool_output") as mock_tool_output:
                commands.cmd_drop("")
                mock_tool_output.assert_called_with("Dropping all files from the chat session.")

            # Verify that all files are dropped
            self.assertEqual(len(coder.abs_fnames), 0)
            self.assertEqual(len(coder.abs_read_only_fnames), 0)

    def test_cmd_load_with_switch_coder(self):
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a temporary file with commands
            commands_file = Path(repo_dir) / "test_commands.txt"
            commands_file.write_text("/ask Tell me about the code\n/model gpt-4\n")

            # Mock run to raise SwitchCoder for /ask and /model
            def mock_run(cmd):
                if cmd.startswith(("/ask", "/model")):
                    raise SwitchCoder()
                return None

            with mock.patch.object(commands, "run", side_effect=mock_run):
                # Capture tool_error output
                with mock.patch.object(io, "tool_error") as mock_tool_error:
                    commands.cmd_load(str(commands_file))

                    # Check that appropriate error messages were shown
                    mock_tool_error.assert_any_call(
                        "Command '/ask Tell me about the code' is only supported in interactive"
                        " mode, skipping."
                    )
                    mock_tool_error.assert_any_call(
                        "Command '/model gpt-4' is only supported in interactive mode, skipping."
                    )

    # Tests for cmd_plan_implementation

    # Sample ticket content for testing plan implementation
    PLAN_SAMPLE_TICKET_CONTENT = """
    ## Goal
    - Implement feature X

    ## Requirements
    - Requirement 1
    - Requirement 2
    """

    def create_test_ticket_file(self, content=None):
        """
        Create a test ticket file with the given content.

        Args:
            content: The content to write to the file. If None, uses PLAN_SAMPLE_TICKET_CONTENT.

        Returns:
            Path: The path to the created file.
        """
        content = content or self.PLAN_SAMPLE_TICKET_CONTENT
        ticket_path = Path(self.tempdir) / "test_ticket.md"
        ticket_path.write_text(content)
        return ticket_path

    def test_cmd_plan_implementation_basic(self):
        """
        Test the basic functionality of cmd_plan_implementation.

        This test verifies that:
        1. The command reads the input file correctly
        2. It creates a PlanCoder instance
        3. It calls PlanCoder.run() with the file content
        4. It saves the generated plan to the expected output file
        5. It displays appropriate messages to the user
        """
        # Setup
        ticket_path = self.create_test_ticket_file()
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with mocked PlanCoder
        with mock.patch("aider.coders.plan_coder.PlanCoder") as mock_plan_coder_class:
            mock_plan_instance = mock_plan_coder_class.return_value
            mock_plan_instance.run.return_value = "Generated implementation plan"

            # Mock Path.write_text to avoid actual file writing
            with mock.patch("pathlib.Path.write_text") as mock_write_text:
                # Mock Path.exists to simulate file creation
                mock_write_text = mock_write_text
                with mock.patch("pathlib.Path.exists", return_value=True):
                    # Mock open to avoid actual file reading
                    with mock.patch(
                        "builtins.open", mock.mock_open(read_data=self.PLAN_SAMPLE_TICKET_CONTENT)
                    ):
                        # Execute
                        commands.cmd_plan_implementation(str(ticket_path))

                        # Verify
                        mock_plan_coder_class.assert_called_once()
                        mock_plan_instance.run.assert_called_once()

    def test_cmd_plan_implementation_reads_file_correctly(self):
        """
        Test that cmd_plan_implementation correctly reads the input file.
        """
        # Setup with custom content
        custom_content = "Custom ticket content"
        ticket_path = self.create_test_ticket_file(custom_content)
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with mocked open function
        with mock.patch("builtins.open", mock.mock_open(read_data=custom_content)) as mock_open:
            mock_open = mock_open
            with mock.patch("aider.coders.plan_coder.PlanCoder") as mock_plan_coder_class:
                # Mock the PlanCoder instance
                mock_plan_instance = mock_plan_coder_class.return_value
                mock_plan_instance.run.return_value = "Generated plan"

                # Mock Path.write_text to avoid actual file writing
                with mock.patch("pathlib.Path.write_text"):
                    # Execute
                    commands.cmd_plan_implementation(str(ticket_path))

                    # Verify PlanCoder was called with the correct content
                    mock_plan_instance.run.assert_called_once_with(custom_content)

    def test_cmd_plan_implementation_creates_correct_plancoder(self):
        """
        Test that cmd_plan_implementation creates the correct PlanCoder instance.
        """
        # Setup
        ticket_path = self.create_test_ticket_file()
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with mocked PlanCoder
        with mock.patch("aider.coders.plan_coder.PlanCoder") as mock_plan_coder_class:
            # Execute
            commands.cmd_plan_implementation(str(ticket_path))

            # Verify PlanCoder was created with correct parameters
            mock_plan_coder_class.assert_called_once_with(
                coder.main_model,
                io,
                repo=coder.repo,
                map_tokens=mock.ANY,
                verbose=commands.verbose,
            )

    def test_cmd_plan_implementation_nonexistent_file(self):
        """
        Test behavior when the input file doesn't exist.
        """
        # Setup
        nonexistent_path = Path(self.tempdir) / "nonexistent.md"
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Execute and verify error message
        with mock.patch.object(io, "tool_error") as mock_tool_error:
            commands.cmd_plan_implementation(str(nonexistent_path))
            mock_tool_error.assert_called_once_with(f"File not found: {nonexistent_path}")

    def test_cmd_plan_implementation_permission_error_reading(self):
        """
        Test behavior with permission issues reading the input file.
        """
        # Setup
        ticket_path = self.create_test_ticket_file()
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Mock open to raise PermissionError
        with mock.patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with mock.patch.object(io, "tool_error") as mock_tool_error:
                # Execute
                commands.cmd_plan_implementation(str(ticket_path))

                # Verify error message
                mock_tool_error.assert_called_once_with(mock.ANY)
                self.assertIn("Permission denied", mock_tool_error.call_args[0][0])

    def test_cmd_plan_implementation_calls_plancoder_run(self):
        """
        Test that PlanCoder.run() is called with the correct parameters.
        """
        # Setup
        ticket_path = self.create_test_ticket_file()
        ticket_content = ticket_path.read_text()
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with mocked PlanCoder
        with mock.patch("aider.coders.plan_coder.PlanCoder") as mock_plan_coder_class:
            mock_plan_instance = mock_plan_coder_class.return_value

            # Execute
            commands.cmd_plan_implementation(str(ticket_path))

            # Verify run was called with correct content
            mock_plan_instance.run.assert_called_once_with(ticket_content)

    def test_cmd_plan_implementation_processes_plancoder_output(self):
        """
        Test that the output from PlanCoder.run() is correctly processed.
        """
        # Setup
        ticket_path = self.create_test_ticket_file()
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)
        expected_plan = "# Implementation Plan\n\n## Steps\n1. Step 1\n2. Step 2"

        # Test with mocked PlanCoder
        with mock.patch("aider.coders.plan_coder.PlanCoder") as mock_plan_coder_class:
            mock_plan_instance = mock_plan_coder_class.return_value
            mock_plan_instance.run.return_value = expected_plan

            # Mock builtins.open for reading
            with mock.patch(
                "builtins.open", mock.mock_open(read_data=self.PLAN_SAMPLE_TICKET_CONTENT)
            ):
                # Mock pathlib.Path.write_text
                with mock.patch("pathlib.Path.write_text") as mock_write_text:
                    mock_write_text = mock_write_text
                    # Mock tool_output to verify success message
                    with mock.patch.object(io, "tool_output") as mock_tool_output:
                        # Execute
                        commands.cmd_plan_implementation(str(ticket_path))

                        # Verify success message was shown
                        mock_tool_output.assert_any_call(mock.ANY)

    def test_cmd_plan_implementation_large_file(self):
        """
        Test with very large input files.
        """
        # Setup
        large_content = "A" * 1000000  # 1MB of content
        ticket_path = self.create_test_ticket_file(large_content)
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Test with mocked PlanCoder
        with mock.patch("aider.coders.plan_coder.PlanCoder") as mock_plan_coder_class:
            mock_plan_instance = mock_plan_coder_class.return_value
            mock_plan_instance.run.return_value = "Large plan"

            # Execute
            commands.cmd_plan_implementation(str(ticket_path))

            # Verify PlanCoder was called with the large content
            mock_plan_instance.run.assert_called_once_with(large_content)

    def test_cmd_plan_implementation_completion(self):
        """
        Test the command's tab completion functionality.
        """
        # Setup
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create test files for completion
        md_file = Path(self.tempdir) / "test.md"
        md_file.touch()
        txt_file = Path(self.tempdir) / "test.txt"
        txt_file.touch()

        # Test with mocked completions_raw_read_only
        with mock.patch.object(commands, "completions_raw_read_only") as mock_completions:
            # Set up the mock to return some completions
            mock_completions.return_value = [
                Completion(text="test.md", start_position=0, display="test.md"),
                Completion(text="test.txt", start_position=0, display="test.txt"),
            ]

            # Create a document with partial command text
            document = Document("/plan-implementation ", cursor_position=20)
            complete_event = mock.MagicMock()

            # Call the method
            if hasattr(commands, "completions_raw_plan_implementation"):
                completions = list(
                    commands.completions_raw_plan_implementation(document, complete_event)
                )

                # Verify that completions_raw_read_only was called with the correct arguments
                mock_completions.assert_called_once()
                self.assertEqual(mock_completions.call_args[0][0], document)
                self.assertEqual(mock_completions.call_args[0][1], complete_event)

                # Verify that the completions were returned correctly
                self.assertEqual(len(completions), 2)
                self.assertEqual(completions[0].text, "test.md")
                self.assertEqual(completions[1].text, "test.txt")

    def test_cmd_raise_pr(self):
        """Test that cmd_raise_pr correctly creates a pull request"""
        with GitTemporaryDirectory() as repo_dir:
            # Create a git repository with a main branch and a feature branch
            repo = git.Repo(repo_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on main branch
            main_file = Path(repo_dir) / "main_file.txt"
            main_file.write_text("Initial content")
            repo.git.add(str(main_file))
            repo.git.commit("-m", "Initial commit on main")

            # Create and switch to feature branch
            repo.git.branch("feature")
            repo.git.checkout("feature")

            # Make changes on feature branch
            feature_file = Path(repo_dir) / "feature_file.txt"
            feature_file.write_text("Feature content")
            repo.git.add(str(feature_file))
            repo.git.commit("-m", "Add feature file")

            # Setup mocks and test objects
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock necessary methods and objects
            with (
                mock.patch.object(commands, "_clear_chat_history") as mock_clear_history,
                mock.patch.object(commands, "_drop_all_files") as mock_drop_files,
                mock.patch.object(commands, "cmd_add") as mock_cmd_add,
                mock.patch("aider.coders.base_coder.Coder.create") as mock_create_coder,
                mock.patch.object(
                    coder.repo, "get_default_branch", return_value="main"
                ) as mock_get_default,
                mock.patch.object(
                    coder.repo, "get_commit_history", return_value="commit1\ncommit2"
                ) as mock_get_history,
                mock.patch.object(
                    coder.repo, "get_changed_files", return_value=["feature_file.txt"]
                ) as mock_get_files,
                mock.patch.object(coder.repo, "raise_pr") as mock_raise_pr,
            ):
                # Create mock context coder
                mock_context_coder = mock.MagicMock()
                mock_context_coder.run.side_effect = ["PR description", "PR title"]
                mock_create_coder.return_value = mock_context_coder

                # Execute the command
                commands.cmd_raise_pr()

                # Verify the command flow
                mock_clear_history.assert_called_once()
                mock_drop_files.assert_called_once()
                mock_get_default.assert_called_once()
                mock_get_history.assert_called()
                mock_get_files.assert_called()
                mock_cmd_add.assert_called()

                # Verify context coder creation and usage
                mock_create_coder.assert_called()
                self.assertEqual(mock_create_coder.call_args[1]["edit_format"], "ask")
                self.assertEqual(mock_create_coder.call_args[1]["summarize_from_coder"], False)

                # Verify PR description and title generation
                self.assertEqual(mock_context_coder.run.call_count, 2)
                description_prompt = mock_context_coder.run.call_args_list[0][0][0]
                self.assertIn("Based on the changes in this branch", description_prompt)
                self.assertIn("commit1\ncommit2", description_prompt)

                title_prompt = mock_context_coder.run.call_args_list[1][0][0]
                self.assertIn("Based on this PR description", title_prompt)
                self.assertIn("PR description", title_prompt)

                # Verify PR creation
                mock_raise_pr.assert_called()

    def test_cmd_raise_pr_error_handling(self):
        """Test that cmd_raise_pr handles errors gracefully"""
        # Test case 1: No git repository
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        coder.repo = None  # Explicitly set repo to None
        commands = Commands(io, coder)

        with mock.patch.object(io, "tool_error") as mock_tool_error:
            commands.cmd_raise_pr()
            mock_tool_error.assert_called_once_with("No git repository found.")

        # Test case 2: Cannot determine default branch
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create a mock repo object
        mock_repo = mock.MagicMock()
        mock_repo.get_default_branch.return_value = None
        coder.repo = mock_repo

        with (
            mock.patch.object(commands, "_clear_chat_history"),
            mock.patch.object(commands, "_drop_all_files"),
            mock.patch.object(io, "tool_error") as mock_tool_error,
        ):
            commands.cmd_raise_pr()
            mock_tool_error.assert_called()

        # Test case 3: Error getting commit history
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create a mock repo object
        mock_repo = mock.MagicMock()
        mock_repo.get_default_branch.return_value = "main"
        mock_repo.get_commit_history.side_effect = git.exc.GitCommandError("git log", 128)
        coder.repo = mock_repo

        with (
            mock.patch.object(commands, "_clear_chat_history"),
            mock.patch.object(commands, "_drop_all_files"),
            mock.patch.object(io, "tool_error") as mock_tool_error,
        ):
            commands.cmd_raise_pr()
            mock_tool_error.assert_called()

        # Test case 4: Error getting changed files
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        coder = Coder.create(self.GPT35, None, io)
        commands = Commands(io, coder)

        # Create a mock repo object
        mock_repo = mock.MagicMock()
        mock_repo.get_default_branch.return_value = "main"
        mock_repo.get_commit_history.return_value = "commit1\ncommit2"
        mock_repo.get_changed_files.side_effect = git.exc.GitCommandError("git diff", 128)
        coder.repo = mock_repo

        with (
            mock.patch.object(commands, "_clear_chat_history"),
            mock.patch.object(commands, "_drop_all_files"),
            mock.patch.object(io, "tool_error") as mock_tool_error,
        ):
            commands.cmd_raise_pr()
            mock_tool_error.assert_called()

    def test_cmd_solve_jira_basic_functionality(self):
        """Test basic execution with a valid JIRA issue key"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the Jira class and its methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(io, "write_text") as mock_write_text,
                mock.patch.object(commands, "cmd_plan_implementation") as mock_plan_implementation,
                mock.patch.object(commands, "_clear_chat_history") as mock_clear_history,
                mock.patch.object(commands, "_drop_all_files") as mock_drop_files,
                mock.patch.object(commands, "cmd_code_from_plan") as mock_code_from_plan,
                mock.patch("os.path.exists", return_value=True),
                mock.patch("os.remove") as mock_remove,
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [
                        {
                            "author": "Test User",
                            "last_updated": "2023-01-01T12:00:00",
                            "comment": "Test comment",
                        }
                    ],
                }

                # Execute the command
                commands.cmd_solve_jira("TEST-123")

                # Verify Jira API was called with the correct issue key
                mock_jira_instance.get_issue_content.assert_called_once_with("TEST-123")

                # Verify the ticket content was written to a file with proper JSON content
                mock_write_text.assert_called_once()
                file_path_arg = mock_write_text.call_args[1]["filename"]
                file_content_arg = mock_write_text.call_args[1]["content"]
                self.assertEqual(file_path_arg, "jira_issue_TEST-123.txt")
                self.assertIn("Test issue summary", file_content_arg)
                self.assertIn("Test issue description", file_content_arg)

                # Verify plan implementation was called with the ticket file
                mock_plan_implementation.assert_called_once_with("jira_issue_TEST-123.txt")

                # Verify chat history was cleared and files were dropped
                mock_clear_history.assert_called_once()
                mock_drop_files.assert_called_once()

                # Verify code_from_plan was called with the implementation plan file
                mock_code_from_plan.assert_called_once()
                self.assertEqual(
                    mock_code_from_plan.call_args[0][0],
                    "jira_issue_TEST-123_implementation_plan.md",
                )

                # Verify temporary files were removed
                mock_remove.assert_any_call("jira_issue_TEST-123.txt")
                mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")

    def test_cmd_solve_jira_with_pr_flag(self):
        """Test execution with the --with-pr flag"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the Jira class and its methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(io, "write_text") as mock_write_text,
                mock.patch.object(commands, "cmd_plan_implementation") as mock_plan_implementation,
                mock.patch.object(commands, "_clear_chat_history") as mock_clear_history,
                mock.patch.object(commands, "_drop_all_files") as mock_drop_files,
                mock.patch.object(commands, "cmd_code_from_plan") as mock_code_from_plan,
                mock.patch.object(commands, "cmd_raise_pr") as mock_raise_pr,
                mock.patch("os.path.exists", return_value=True),
                mock.patch("os.remove") as mock_remove,
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [
                        {
                            "author": "Test User",
                            "last_updated": "2023-01-01T12:00:00",
                            "comment": "Test comment",
                        }
                    ],
                }

                # Execute the command with --with-pr flag
                commands.cmd_solve_jira("TEST-123 --with-pr")

                # Verify Jira API was called with the correct issue key
                mock_jira_instance.get_issue_content.assert_called_once_with("TEST-123")

                # Verify the ticket content was written to a file
                mock_write_text.assert_called_once()
                file_path_arg = mock_write_text.call_args[1]["filename"]
                self.assertEqual(file_path_arg, "jira_issue_TEST-123.txt")

                # Verify plan implementation was called with the ticket file
                mock_plan_implementation.assert_called_once_with("jira_issue_TEST-123.txt")

                # Verify chat history was cleared and files were dropped
                mock_clear_history.assert_called_once()
                mock_drop_files.assert_called_once()

                # Verify code_from_plan was called with the implementation plan file
                mock_code_from_plan.assert_called_once()
                self.assertEqual(
                    mock_code_from_plan.call_args[0][0],
                    "jira_issue_TEST-123_implementation_plan.md",
                )

                # Verify temporary files were removed
                mock_remove.assert_any_call("jira_issue_TEST-123.txt")
                mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")

                # Verify that cmd_raise_pr was called to create a pull request
                mock_raise_pr.assert_called_once()

    def test_cmd_solve_jira_with_short_pr_flag(self):
        """Test execution with the -pr flag"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the Jira class and its methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(io, "write_text") as mock_write_text,
                mock.patch.object(commands, "cmd_plan_implementation") as mock_plan_implementation,
                mock.patch.object(commands, "_clear_chat_history") as mock_clear_history,
                mock.patch.object(commands, "_drop_all_files") as mock_drop_files,
                mock.patch.object(commands, "cmd_code_from_plan") as mock_code_from_plan,
                mock.patch.object(commands, "cmd_raise_pr") as mock_raise_pr,
                mock.patch("os.path.exists", return_value=True),
                mock.patch("os.remove") as mock_remove,
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [
                        {
                            "author": "Test User",
                            "last_updated": "2023-01-01T12:00:00",
                            "comment": "Test comment",
                        }
                    ],
                }

                # Execute the command with -pr flag (short form)
                commands.cmd_solve_jira("TEST-123 -pr")

                # Verify Jira API was called with the correct issue key
                mock_jira_instance.get_issue_content.assert_called_once_with("TEST-123")

                # Verify the ticket content was written to a file
                mock_write_text.assert_called_once()
                file_path_arg = mock_write_text.call_args[1]["filename"]
                self.assertEqual(file_path_arg, "jira_issue_TEST-123.txt")

                # Verify plan implementation was called with the ticket file
                mock_plan_implementation.assert_called_once_with("jira_issue_TEST-123.txt")

                # Verify chat history was cleared and files were dropped
                mock_clear_history.assert_called_once()
                mock_drop_files.assert_called_once()

                # Verify code_from_plan was called with the implementation plan file
                mock_code_from_plan.assert_called_once()
                self.assertEqual(
                    mock_code_from_plan.call_args[0][0],
                    "jira_issue_TEST-123_implementation_plan.md",
                )

                # Verify temporary files were removed
                mock_remove.assert_any_call("jira_issue_TEST-123.txt")
                mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")

                # Verify that cmd_raise_pr was called to create a pull request
                mock_raise_pr.assert_called_once()

    def test_cmd_solve_jira_no_issue_key(self):
        """Test error handling when no issue key is provided"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the tool_error method to verify it's called with the correct message
            with mock.patch.object(io, "tool_error") as mock_tool_error:
                # Execute the command with no issue key
                commands.cmd_solve_jira("")

                # Verify that tool_error was called with the expected message
                mock_tool_error.assert_called_once_with("Please provide a JIRA issue key or ID")

            # Test with only flags but no issue key
            with mock.patch.object(io, "tool_error") as mock_tool_error:
                # Execute the command with only the --with-pr flag
                commands.cmd_solve_jira("--with-pr")

                # Verify that tool_error was called with the expected message
                mock_tool_error.assert_called_once_with("Please provide a JIRA issue key or ID")

            # Test with only flags but no issue key (short form)
            with mock.patch.object(io, "tool_error") as mock_tool_error:
                # Execute the command with only the -pr flag
                commands.cmd_solve_jira("-pr")

                # Verify that tool_error was called with the expected message
                mock_tool_error.assert_called_once_with("Please provide a JIRA issue key or ID")

    def test_cmd_solve_jira_file_operations(self):
        """Test file creation and deletion operations"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the Jira class and its methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(io, "write_text") as mock_write_text,
                mock.patch("os.path.exists", return_value=True),
                mock.patch("os.remove") as mock_remove,
                mock.patch.object(commands, "_clear_chat_history"),
                mock.patch.object(commands, "_drop_all_files"),
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [
                        {
                            "author": "Test User",
                            "last_updated": "2023-01-01T12:00:00",
                            "comment": "Test comment",
                        }
                    ],
                }

                # Create a mock repo
                mock_repo = mock.MagicMock()
                coder.repo = mock_repo

                # Execute the command
                commands.cmd_solve_jira("TEST-123")

                # Verify file creation
                mock_write_text.assert_called_once()
                file_path_arg = mock_write_text.call_args[1]["filename"]
                self.assertEqual(file_path_arg, "jira_issue_TEST-123.txt")

                # Verify file deletion
                mock_remove.assert_any_call("jira_issue_TEST-123.txt")
                mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")
                self.assertEqual(mock_remove.call_count, 2)

                # Test with repo operations
                mock_repo.reset_mock()
                mock_write_text.reset_mock()
                mock_remove.reset_mock()

                # Execute the command again
                commands.cmd_solve_jira("TEST-123")

                # Verify file creation and deletion with repo operations
                mock_write_text.assert_called_once()
                mock_remove.assert_any_call("jira_issue_TEST-123.txt")
                mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")

    def test_cmd_solve_jira_git_commits(self):
        """Test that appropriate git commits are made"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock the Jira class and its methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch("os.path.exists", return_value=True),
                mock.patch.object(commands, "_clear_chat_history"),
                mock.patch.object(commands, "_drop_all_files"),
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [
                        {
                            "author": "Test User",
                            "last_updated": "2023-01-01T12:00:00",
                            "comment": "Test comment",
                        }
                    ],
                }

                # Create a mock repo
                mock_repo = mock.MagicMock()
                coder.repo = mock_repo

                # Execute the command
                commands.cmd_solve_jira("TEST-123")

                # Verify that commits were made for the implementation plan
                mock_repo.commit.assert_any_call(
                    fnames=["jira_issue_TEST-123_implementation_plan.md"],
                    message="Add implementation plan for JIRA issue TEST-123",
                    aider_edits=True,
                )

                # Verify that commits were made for deleting the implementation plan
                mock_repo.commit.assert_any_call(
                    fnames=["jira_issue_TEST-123_implementation_plan.md"],
                    message="Delete implementation plan for JIRA issue TEST-123 from git",
                    aider_edits=True,
                )

                # Verify that commits were made for deleting the JIRA ticket file
                mock_repo.commit.assert_any_call(
                    fnames=["jira_issue_TEST-123.txt"],
                    message="Remove JIRA ticket file for issue TEST-123",
                    aider_edits=True,
                )

                # Verify the total number of commits made
                self.assertEqual(mock_repo.commit.call_count, 3)

    def test_cmd_solve_jira_command_flow(self):
        """Test that all required commands are called in the correct order"""
        with GitTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create a mock manager to track the order of method calls
            mock_manager = mock.MagicMock()

            # Mock the Jira class and its methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(io, "write_text") as mock_write_text,
                mock.patch.object(commands, "cmd_plan_implementation") as mock_plan_implementation,
                mock.patch.object(commands, "_clear_chat_history") as mock_clear_history,
                mock.patch.object(commands, "_drop_all_files") as mock_drop_files,
                mock.patch.object(commands, "cmd_code_from_plan") as mock_code_from_plan,
                mock.patch("os.path.exists", return_value=True),
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [
                        {
                            "author": "Test User",
                            "last_updated": "2023-01-01T12:00:00",
                            "comment": "Test comment",
                        }
                    ],
                }

                # Set up side effects to track call order
                mock_write_text.side_effect = lambda **kwargs: mock_manager.write_text(**kwargs)
                mock_plan_implementation.side_effect = (
                    lambda *args: mock_manager.plan_implementation(*args)
                )
                mock_clear_history.side_effect = lambda: mock_manager.clear_history()
                mock_drop_files.side_effect = lambda: mock_manager.drop_files()
                mock_code_from_plan.side_effect = (
                    lambda *args, **kwargs: mock_manager.code_from_plan(*args, **kwargs)
                )

                # Execute the command
                commands.cmd_solve_jira("TEST-123")

                # Verify the correct sequence of method calls
                mock_calls = mock_manager.mock_calls
                call_names = [call[0] for call in mock_calls]

                # Check that write_text is called first (to create the ticket file)
                self.assertEqual(call_names[0], "write_text")

                # Check that plan_implementation is called next
                self.assertEqual(call_names[1], "plan_implementation")
                self.assertEqual(
                    mock_plan_implementation.call_args[0][0], "jira_issue_TEST-123.txt"
                )

                # Check that clear_history and drop_files are called before code_from_plan
                self.assertIn("clear_history", call_names)
                self.assertIn("drop_files", call_names)
                clear_index = call_names.index("clear_history")
                drop_index = call_names.index("drop_files")
                code_index = call_names.index("code_from_plan")

                # Verify the order: clear_history -> drop_files -> code_from_plan
                self.assertLess(clear_index, code_index)
                self.assertLess(drop_index, code_index)

                # Check that code_from_plan is called with the correct implementation plan file
                self.assertEqual(
                    mock_code_from_plan.call_args[0][0],
                    "jira_issue_TEST-123_implementation_plan.md",
                )

    def test_cmd_solve_jira_file_cleanup(self):
        """Test that temporary files are properly cleaned up"""
        with GitTemporaryDirectory() as repo_dir:
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Create test files to simulate the files that should be cleaned up
            ticket_file = Path(repo_dir) / "jira_issue_TEST-123.txt"
            ticket_file.write_text("Test ticket content")

            plan_file = Path(repo_dir) / "jira_issue_TEST-123_implementation_plan.md"
            plan_file.write_text("# Implementation Plan\n\n## Steps\n1. Step 1\n2. Step 2")

            # Mock the necessary methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(commands, "cmd_plan_implementation"),
                mock.patch.object(commands, "_clear_chat_history"),
                mock.patch.object(commands, "_drop_all_files"),
                mock.patch.object(commands, "cmd_code_from_plan"),
                mock.patch("os.remove") as mock_remove,
                mock.patch("os.path.exists", return_value=True),
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description",
                    "comments": [],
                }

                # Execute the command
                commands.cmd_solve_jira("TEST-123")

                # Verify that os.remove was called for both temporary files
                mock_remove.assert_any_call("jira_issue_TEST-123.txt")
                mock_remove.assert_any_call("jira_issue_TEST-123_implementation_plan.md")
                self.assertEqual(mock_remove.call_count, 2)

                # Test with file not found scenario
                mock_remove.reset_mock()
                mock_remove.side_effect = FileNotFoundError("File not found")

                with mock.patch.object(io, "tool_error") as mock_tool_error:
                    commands.cmd_solve_jira("TEST-123")

                    # Verify that tool_error was called when file removal fails
                    self.assertEqual(mock_remove.call_count, 2)
                    mock_tool_error.assert_any_call(mock.ANY)

                # Test with permission error scenario
                mock_remove.reset_mock()
                mock_remove.side_effect = PermissionError("Permission denied")

                with mock.patch.object(io, "tool_error") as mock_tool_error:
                    commands.cmd_solve_jira("TEST-123")

                    # Verify that tool_error was called when file removal fails
                    self.assertEqual(mock_remove.call_count, 2)
                    mock_tool_error.assert_any_call(mock.ANY)

    def test_cmd_raise_pr_with_template(self):
        """Test that cmd_raise_pr correctly uses PR templates when available"""
        with GitTemporaryDirectory() as repo_dir:
            # Create a git repository with a main branch and a feature branch
            repo = git.Repo(repo_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on main branch
            main_file = Path(repo_dir) / "main_file.txt"
            main_file.write_text("Initial content")
            repo.git.add(str(main_file))
            repo.git.commit("-m", "Initial commit on main")

            # Create and switch to feature branch
            repo.git.branch("feature")
            repo.git.checkout("feature")

            # Make changes on feature branch
            feature_file = Path(repo_dir) / "feature_file.txt"
            feature_file.write_text("Feature content")
            repo.git.add(str(feature_file))
            repo.git.commit("-m", "Add feature file")

            # Create a PR template file
            github_dir = Path(repo_dir) / ".github"
            github_dir.mkdir(exist_ok=True)
            template_path = github_dir / "pull_request_template.md"
            template_content = "## PR Template\n\nPlease describe your changes."
            template_path.write_text(template_content)
            repo.git.add(str(template_path))
            repo.git.commit("-m", "Add PR template")

            # Setup mocks and test objects
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock necessary methods and objects
            with (
                mock.patch.object(commands, "_clear_chat_history"),
                mock.patch.object(commands, "_drop_all_files"),
                mock.patch.object(commands, "cmd_add"),
                mock.patch("aider.coders.base_coder.Coder.create") as mock_create_coder,
                mock.patch.object(coder.repo, "get_default_branch", return_value="main"),
                mock.patch.object(
                    coder.repo, "get_commit_history", return_value="commit1\ncommit2"
                ),
                mock.patch.object(
                    coder.repo, "get_changed_files", return_value=["feature_file.txt"]
                ),
                mock.patch.object(
                    coder.repo, "find_pr_template", return_value=str(template_path)
                ) as mock_find_template,
                mock.patch.object(coder.repo, "raise_pr") as mock_raise_pr,
            ):
                # Create mock context coder
                mock_context_coder = mock.MagicMock()
                mock_context_coder.run.side_effect = ["PR description", "PR title"]
                mock_create_coder.return_value = mock_context_coder

                # Execute the command
                commands.cmd_raise_pr()

                # Verify that find_pr_template was called
                mock_find_template.assert_called_once()

                # Verify PR creation with template
                mock_raise_pr.assert_called_once()

    def test_cmd_raise_pr_with_multiple_templates(self):
        """Test that cmd_raise_pr correctly handles multiple PR templates"""
        with GitTemporaryDirectory() as repo_dir:
            # Create a git repository with a main branch and a feature branch
            repo = git.Repo(repo_dir)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create a file and make initial commit on main branch
            main_file = Path(repo_dir) / "main_file.txt"
            main_file.write_text("Initial content")
            repo.git.add(str(main_file))
            repo.git.commit("-m", "Initial commit on main")

            # Create and switch to feature branch
            repo.git.branch("feature")
            repo.git.checkout("feature")

            # Make changes on feature branch
            feature_file = Path(repo_dir) / "feature_file.txt"
            feature_file.write_text("Feature content")
            repo.git.add(str(feature_file))
            repo.git.commit("-m", "Add feature file")

            # Create multiple PR template files
            github_dir = Path(repo_dir) / ".github"
            github_dir.mkdir(exist_ok=True)
            template_dir = github_dir / "PULL_REQUEST_TEMPLATE"
            template_dir.mkdir(exist_ok=True)

            feature_template = template_dir / "feature.md"
            feature_template.write_text("## Feature Template\n\nDescribe the new feature.")

            bugfix_template = template_dir / "bugfix.md"
            bugfix_template.write_text("## Bug Fix Template\n\nDescribe the bug that was fixed.")

            repo.git.add(str(feature_template))
            repo.git.add(str(bugfix_template))
            repo.git.commit("-m", "Add multiple PR templates")

            # Setup mocks and test objects
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Mock necessary methods and objects
            with (
                mock.patch.object(commands, "_clear_chat_history"),
                mock.patch.object(commands, "_drop_all_files"),
                mock.patch.object(commands, "cmd_add"),
                mock.patch("aider.coders.base_coder.Coder.create") as mock_create_coder,
                mock.patch.object(coder.repo, "get_default_branch", return_value="main"),
                mock.patch.object(
                    coder.repo, "get_commit_history", return_value="commit1\ncommit2"
                ),
                mock.patch.object(
                    coder.repo, "get_changed_files", return_value=["feature_file.txt"]
                ),
                mock.patch.object(
                    coder.repo,
                    "find_pr_template",
                    return_value=[str(feature_template), str(bugfix_template)],
                ) as mock_find_template,
                mock.patch.object(coder.repo, "raise_pr") as mock_raise_pr,
            ):
                # Create mock context coder
                mock_context_coder = mock.MagicMock()
                mock_context_coder.run.side_effect = ["PR description", "PR title"]
                mock_create_coder.return_value = mock_context_coder

                # Execute the command
                commands.cmd_raise_pr()

                # Verify that find_pr_template was called
                mock_find_template.assert_called_once()

                # Verify PR creation with selected template
                mock_raise_pr.assert_called_once()
                # Check that the models were passed to the repo for template selection
                self.assertEqual(coder.repo.models, coder.models)
                self.assertEqual(coder.repo.io, io)

    def test_cmd_solve_jira_no_repo(self):
        """Test behavior when no git repository is available"""
        with ChdirTemporaryDirectory() as repo_dir:
            repo_dir = repo_dir
            io = InputOutput(pretty=False, fancy_input=False, yes=True)
            coder = Coder.create(self.GPT35, None, io)
            commands = Commands(io, coder)

            # Ensure there's no repo
            self.assertIsNone(coder.repo)

            # Mock the necessary methods
            with (
                mock.patch("aider.jira.Jira") as mock_jira_class,
                mock.patch.object(io, "write_text") as mock_write_text,
                mock.patch.object(commands, "cmd_plan_implementation") as mock_plan_implementation,
                mock.patch.object(commands, "_clear_chat_history") as mock_clear_history,
                mock.patch.object(commands, "_drop_all_files") as mock_drop_files,
                mock.patch.object(commands, "cmd_code_from_plan") as mock_code_from_plan,
                mock.patch("os.path.exists", return_value=True),
            ):
                # Set up the mock Jira instance
                mock_jira_instance = mock_jira_class.return_value
                mock_jira_instance.get_issue_content.return_value = {
                    "summary": "Test issue summary",
                    "description": "Test issue description with requirements",
                    "comments": [],
                }

                # Execute the command
                commands.cmd_solve_jira("TEST-123")

                # Verify that the command still works without a repo
                mock_jira_instance.get_issue_content.assert_called_once_with("TEST-123")
                mock_write_text.assert_called_once()
                mock_plan_implementation.assert_called_once()
                mock_clear_history.assert_called_once()
                mock_drop_files.assert_called_once()
                mock_code_from_plan.assert_called_once()
