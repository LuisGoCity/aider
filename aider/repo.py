import os
import subprocess
import time
from pathlib import Path, PurePosixPath

try:
    import git

    ANY_GIT_ERROR = [
        git.exc.ODBError,
        git.exc.GitError,
        git.exc.InvalidGitRepositoryError,
        git.exc.GitCommandNotFound,
    ]
except ImportError:
    git = None
    ANY_GIT_ERROR = []

import pathspec

from aider import prompts, utils

from .dump import dump  # noqa: F401

ANY_GIT_ERROR += [
    OSError,
    IndexError,
    BufferError,
    TypeError,
    ValueError,
    AttributeError,
    AssertionError,
    TimeoutError,
]
ANY_GIT_ERROR = tuple(ANY_GIT_ERROR)


class GitRepo:
    repo = None
    aider_ignore_file = None
    aider_ignore_spec = None
    aider_ignore_ts = 0
    aider_ignore_last_check = 0
    subtree_only = False
    ignore_file_cache = {}
    git_repo_error = None

    def __init__(
        self,
        io,
        fnames,
        git_dname,
        aider_ignore_file=None,
        models=None,
        attribute_author=True,
        attribute_committer=True,
        attribute_commit_message_author=False,
        attribute_commit_message_committer=False,
        commit_prompt=None,
        subtree_only=False,
        git_commit_verify=True,
    ):
        self.io = io
        self.models = models

        self.normalized_path = {}
        self.tree_files = {}

        self.attribute_author = attribute_author
        self.attribute_committer = attribute_committer
        self.attribute_commit_message_author = attribute_commit_message_author
        self.attribute_commit_message_committer = attribute_commit_message_committer
        self.commit_prompt = commit_prompt
        self.subtree_only = subtree_only
        self.git_commit_verify = git_commit_verify
        self.ignore_file_cache = {}

        if git_dname:
            check_fnames = [git_dname]
        elif fnames:
            check_fnames = fnames
        else:
            check_fnames = ["."]

        repo_paths = []
        for fname in check_fnames:
            fname = Path(fname)
            fname = fname.resolve()

            if not fname.exists() and fname.parent.exists():
                fname = fname.parent

            try:
                repo_path = git.Repo(fname, search_parent_directories=True).working_dir
                repo_path = utils.safe_abs_path(repo_path)
                repo_paths.append(repo_path)
            except ANY_GIT_ERROR:
                pass

        num_repos = len(set(repo_paths))

        if num_repos == 0:
            raise FileNotFoundError
        if num_repos > 1:
            self.io.tool_error("Files are in different git repos.")
            raise FileNotFoundError

        # https://github.com/gitpython-developers/GitPython/issues/427
        self.repo = git.Repo(repo_paths.pop(), odbt=git.GitDB)
        self.root = utils.safe_abs_path(self.repo.working_tree_dir)

        if aider_ignore_file:
            self.aider_ignore_file = Path(aider_ignore_file)

    def commit(self, fnames=None, context=None, message=None, aider_edits=False):
        if not fnames and not self.repo.is_dirty():
            return

        diffs = self.get_diffs(fnames)
        if not diffs:
            return

        if message:
            commit_message = message
        else:
            commit_message = self.get_commit_message(diffs, context)

        if aider_edits and self.attribute_commit_message_author:
            commit_message = "aider: " + commit_message
        elif self.attribute_commit_message_committer:
            commit_message = "aider: " + commit_message

        if not commit_message:
            commit_message = "(no commit message provided)"

        full_commit_message = commit_message
        # if context:
        #    full_commit_message += "\n\n# Aider chat conversation:\n\n" + context

        cmd = ["-m", full_commit_message]
        if not self.git_commit_verify:
            cmd.append("--no-verify")
        if fnames:
            fnames = [str(self.abs_root_path(fn)) for fn in fnames]
            for fname in fnames:
                try:
                    self.repo.git.add(fname)
                except ANY_GIT_ERROR as err:
                    self.io.tool_error(f"Unable to add {fname}: {err}")
            cmd += ["--"] + fnames
        else:
            cmd += ["-a"]

        original_user_name = self.repo.git.config("--get", "user.name")
        original_committer_name_env = os.environ.get("GIT_COMMITTER_NAME")
        committer_name = f"{original_user_name} (aider)"

        if self.attribute_committer:
            os.environ["GIT_COMMITTER_NAME"] = committer_name

        if aider_edits and self.attribute_author:
            original_author_name_env = os.environ.get("GIT_AUTHOR_NAME")
            os.environ["GIT_AUTHOR_NAME"] = committer_name

        try:
            self.repo.git.commit(cmd)
            commit_hash = self.get_head_commit_sha(short=True)
            self.io.tool_output(f"Commit {commit_hash} {commit_message}", bold=True)
            return commit_hash, commit_message
        except ANY_GIT_ERROR as err:
            self.io.tool_error(f"Unable to commit: {err}")
        finally:
            # Restore the env

            if self.attribute_committer:
                if original_committer_name_env is not None:
                    os.environ["GIT_COMMITTER_NAME"] = original_committer_name_env
                else:
                    del os.environ["GIT_COMMITTER_NAME"]

            if aider_edits and self.attribute_author:
                if original_author_name_env is not None:
                    os.environ["GIT_AUTHOR_NAME"] = original_author_name_env
                else:
                    del os.environ["GIT_AUTHOR_NAME"]

    def get_rel_repo_dir(self):
        try:
            return os.path.relpath(self.repo.git_dir, os.getcwd())
        except (ValueError, OSError):
            return self.repo.git_dir

    def get_commit_message(self, diffs, context):
        diffs = "# Diffs:\n" + diffs

        content = ""
        if context:
            content += context + "\n"
        content += diffs

        system_content = self.commit_prompt or prompts.commit_system
        messages = [
            dict(role="system", content=system_content),
            dict(role="user", content=content),
        ]

        commit_message = None
        for model in self.models:
            num_tokens = model.token_count(messages)
            max_tokens = model.info.get("max_input_tokens") or 0
            if max_tokens and num_tokens > max_tokens:
                continue
            commit_message = model.simple_send_with_retries(messages)
            if commit_message:
                break

        if not commit_message:
            self.io.tool_error("Failed to generate commit message!")
            return

        commit_message = commit_message.strip()
        if commit_message and commit_message[0] == '"' and commit_message[-1] == '"':
            commit_message = commit_message[1:-1].strip()

        return commit_message

    def get_diffs(self, fnames=None):
        # We always want diffs of index and working dir

        current_branch_has_commits = False
        try:
            active_branch = self.repo.active_branch
            try:
                commits = self.repo.iter_commits(active_branch)
                current_branch_has_commits = any(commits)
            except ANY_GIT_ERROR:
                pass
        except (TypeError,) + ANY_GIT_ERROR:
            pass

        if not fnames:
            fnames = []

        diffs = ""
        for fname in fnames:
            if not self.path_in_repo(fname):
                diffs += f"Added {fname}\n"

        try:
            if current_branch_has_commits:
                args = ["HEAD", "--"] + list(fnames)
                diffs += self.repo.git.diff(*args)
                return diffs

            wd_args = ["--"] + list(fnames)
            index_args = ["--cached"] + wd_args

            diffs += self.repo.git.diff(*index_args)
            diffs += self.repo.git.diff(*wd_args)

            return diffs
        except ANY_GIT_ERROR as err:
            self.io.tool_error(f"Unable to diff: {err}")

    def diff_commits(self, pretty, from_commit, to_commit):
        args = []
        if pretty:
            args += ["--color"]
        else:
            args += ["--color=never"]

        args += [from_commit, to_commit]
        diffs = self.repo.git.diff(*args)

        return diffs

    def get_tracked_files(self):
        if not self.repo:
            return []

        try:
            commit = self.repo.head.commit
        except ValueError:
            commit = None
        except ANY_GIT_ERROR as err:
            self.git_repo_error = err
            self.io.tool_error(f"Unable to list files in git repo: {err}")
            self.io.tool_output("Is your git repo corrupted?")
            return []

        files = set()
        if commit:
            if commit in self.tree_files:
                files = self.tree_files[commit]
            else:
                try:
                    iterator = commit.tree.traverse()
                    blob = None  # Initialize blob
                    while True:
                        try:
                            blob = next(iterator)
                            if blob.type == "blob":  # blob is a file
                                files.add(blob.path)
                        except IndexError:
                            # Handle potential index error during tree traversal
                            # without relying on potentially unassigned 'blob'
                            self.io.tool_warning(
                                "GitRepo: Index error encountered while reading git tree object."
                                " Skipping."
                            )
                            continue
                        except StopIteration:
                            break
                except ANY_GIT_ERROR as err:
                    self.git_repo_error = err
                    self.io.tool_error(f"Unable to list files in git repo: {err}")
                    self.io.tool_output("Is your git repo corrupted?")
                    return []
                files = set(self.normalize_path(path) for path in files)
                self.tree_files[commit] = set(files)

        # Add staged files
        index = self.repo.index
        try:
            staged_files = [path for path, _ in index.entries.keys()]
            files.update(self.normalize_path(path) for path in staged_files)
        except ANY_GIT_ERROR as err:
            self.io.tool_error(f"Unable to read staged files: {err}")

        res = [fname for fname in files if not self.ignored_file(fname)]

        return res

    def normalize_path(self, path):
        orig_path = path
        res = self.normalized_path.get(orig_path)
        if res:
            return res

        path = str(Path(PurePosixPath((Path(self.root) / path).relative_to(self.root))))
        self.normalized_path[orig_path] = path
        return path

    def refresh_aider_ignore(self):
        if not self.aider_ignore_file:
            return

        current_time = time.time()
        if current_time - self.aider_ignore_last_check < 1:
            return

        self.aider_ignore_last_check = current_time

        if not self.aider_ignore_file.is_file():
            return

        mtime = self.aider_ignore_file.stat().st_mtime
        if mtime != self.aider_ignore_ts:
            self.aider_ignore_ts = mtime
            self.ignore_file_cache = {}
            lines = self.aider_ignore_file.read_text().splitlines()
            self.aider_ignore_spec = pathspec.PathSpec.from_lines(
                pathspec.patterns.GitWildMatchPattern,
                lines,
            )

    def git_ignored_file(self, path):
        if not self.repo:
            return
        try:
            if self.repo.ignored(path):
                return True
        except ANY_GIT_ERROR:
            return False

    def ignored_file(self, fname):
        self.refresh_aider_ignore()

        if fname in self.ignore_file_cache:
            return self.ignore_file_cache[fname]

        result = self.ignored_file_raw(fname)
        self.ignore_file_cache[fname] = result
        return result

    def ignored_file_raw(self, fname):
        if self.subtree_only:
            try:
                fname_path = Path(self.normalize_path(fname))
                cwd_path = Path.cwd().resolve().relative_to(Path(self.root).resolve())
            except ValueError:
                # Issue #1524
                # ValueError: 'C:\\dev\\squid-certbot' is not in the subpath of
                # 'C:\\dev\\squid-certbot'
                # Clearly, fname is not under cwd... so ignore it
                return True

            if cwd_path not in fname_path.parents and fname_path != cwd_path:
                return True

        if not self.aider_ignore_file or not self.aider_ignore_file.is_file():
            return False

        try:
            fname = self.normalize_path(fname)
        except ValueError:
            return True

        return self.aider_ignore_spec.match_file(fname)

    def path_in_repo(self, path):
        if not self.repo:
            return
        if not path:
            return

        tracked_files = set(self.get_tracked_files())
        return self.normalize_path(path) in tracked_files

    def abs_root_path(self, path):
        res = Path(self.root) / path
        return utils.safe_abs_path(res)

    def get_dirty_files(self):
        """
        Returns a list of all files which are dirty (not committed), either staged or in the working
        directory.
        """
        dirty_files = set()

        # Get staged files
        staged_files = self.repo.git.diff("--name-only", "--cached").splitlines()
        dirty_files.update(staged_files)

        # Get unstaged files
        unstaged_files = self.repo.git.diff("--name-only").splitlines()
        dirty_files.update(unstaged_files)

        return list(dirty_files)

    def is_dirty(self, path=None):
        if path and not self.path_in_repo(path):
            return True

        return self.repo.is_dirty(path=path)

    def get_head_commit(self):
        try:
            return self.repo.head.commit
        except (ValueError,) + ANY_GIT_ERROR:
            return None

    def get_head_commit_sha(self, short=False):
        commit = self.get_head_commit()
        if not commit:
            return
        if short:
            return commit.hexsha[:7]
        return commit.hexsha

    def get_head_commit_message(self, default=None):
        commit = self.get_head_commit()
        if not commit:
            return default
        return commit.message

    def get_default_branch(self):
        """Determine the default branch (main or master)"""
        for branch_name in ["main", "master"]:
            try:
                self.repo.git.rev_parse(f"--verify {branch_name}")
                return branch_name
            except ANY_GIT_ERROR:
                continue
        return None

    def get_commit_history(self, base_branch, compare_branch):
        """Get commit history between two branches"""
        try:
            return self.repo.git.log(
                f"{base_branch}..{compare_branch}", "--pretty=format:%h %s", "--no-merges"
            )
        except ANY_GIT_ERROR as e:
            raise e

    def get_changed_files(self, base_branch, compare_branch):
        """Get list of files changed between two branches"""
        try:
            return self.repo.git.diff(
                f"{base_branch}..{compare_branch}", "--name-only"
            ).splitlines()
        except ANY_GIT_ERROR as e:
            raise e

    def push_commited_changes(self, branch_name=None):
        """
        Push committed changes to the remote repository.

        Args:
            branch_name (str, optional): The name of the branch to push. If None,
                                        attempts to detect the current branch.

        Returns:
            tuple: (success, error_message) where success is a boolean indicating if
                  the push was successful, and error_message is a string with details
                  if the push failed (None if successful).
        """
        if not branch_name:
            branch_name = self.repo.active_branch.name

        if branch_name:
            cmd = ["git", "push", "origin", "-u", branch_name]
        else:
            # Fallback to original behavior if branch name cannot be determined
            cmd = ["git", "push", "-u", "origin"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if "Authentication failed" in error_msg:
                    self.io.tool_error("Git authentication failed. Please check your credentials.")
                    return False, "Git authentication failed. Please check your credentials."
                elif "could not read Username" in error_msg:
                    self.io.tool_error(
                        "Git credentials not found. Please configure your git credentials."
                    )
                    return (
                        False,
                        "Git credentials not found. Please configure your git credentials.",
                    )
                elif "Connection timed out" in error_msg or "Could not resolve host" in error_msg:
                    self.io.tool_error(
                        "Network error while pushing to remote. Please check your connection."
                    )
                    return (
                        False,
                        "Network error while pushing to remote. Please check your connection.",
                    )
                else:
                    self.io.tool_error(f"Git push failed: {error_msg}")
                    return False, f"Git push failed: {error_msg}"

            return True, None

        except subprocess.SubprocessError as e:
            self.io.tool_error(f"Error executing git push command: {str(e)}")
            return False, f"Error executing git push command: {str(e)}"

    def find_pr_template(self):
        """
        Search for PR templates in the repository.

        Looks for "pull_request_template.md" (case insensitive) in:
        - Root directory
        - docs/ directory
        - .github/ directory
        - Any PULL_REQUEST_TEMPLATE/ subdirectory in the above locations

        Returns:
            str or list: Path to a single template if only one is found,
                         or a list of template paths if multiple are found in a
                         PULL_REQUEST_TEMPLATE directory, or None if no templates are found.
        """
        template_locations = [
            self.root,  # Root directory
            os.path.join(self.root, "docs"),  # docs/ directory
            os.path.join(self.root, ".github"),  # .github/ directory
        ]

        # Add PULL_REQUEST_TEMPLATE subdirectories
        for location in template_locations.copy():
            pr_template_dir = os.path.join(location, "PULL_REQUEST_TEMPLATE")
            if os.path.isdir(pr_template_dir):
                template_locations.append(pr_template_dir)

        templates_found = []

        # Search for templates in all locations
        for location in template_locations:
            if not os.path.isdir(location):
                continue

            # Look for pull_request_template.md (case insensitive)
            for filename in os.listdir(location):
                if filename.lower() == "pull_request_template.md":
                    templates_found.append(os.path.join(location, filename))

            # If we're in a PULL_REQUEST_TEMPLATE directory, also look for any .md files
            if os.path.basename(location) == "PULL_REQUEST_TEMPLATE":
                for filename in os.listdir(location):
                    if (
                        filename.lower().endswith(".md")
                        and os.path.join(location, filename) not in templates_found
                    ):
                        templates_found.append(os.path.join(location, filename))

        if not templates_found:
            return None
        elif len(templates_found) == 1:
            return templates_found[0]
        else:
            return templates_found

    def raise_pr(self, base_branch, compare_branch, pr_title, pr_description):
        """Raise a PR via the git cli."""
        # Check if GitHub CLI is available
        gh_available = False
        try:
            subprocess.run(["gh", "--version"], check=True, capture_output=True)
            gh_available = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        if gh_available:
            # Push changes to remote with the specific branch name
            success, error_message = self.push_commited_changes(branch_name=compare_branch.name)
            if not success:
                self.io.tool_error(f"Failed to push changes before creating PR: {error_message}")
                return False
            cmd = [
                "gh",
                "pr",
                "create",
                "--base",
                str(base_branch),
                "--head",
                str(compare_branch),
                "--title",
                pr_title,
                "--body",
                pr_description,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                pr_url = result.stdout.strip()
                self.io.tool_output(f"PR created successfully: {pr_url}")
                return True
            else:
                self.io.tool_error(f"Failed to create PR: {result.stderr}")
                return False
        else:
            self.io.tool_error("GitHub CLI (gh) not found. Please install it to create PRs.")
            self.io.tool_output("You can create the PR manually using this description.")
            raise Exception("Failed to raise PR.")
