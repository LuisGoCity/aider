# Task Outline

Implement functionality to detect and select PR templates when raising pull requests in the aider tool. The system should search for "pull_request_template.md" in the root, docs, .github directories, and any PULL_REQUEST_TEMPLATE subdirectories. When multiple templates are found in a PULL_REQUEST_TEMPLATE directory, an LLM call should be made to select the appropriate template. The implementation must maintain simplicity with clear separation of concerns.

# Steps

1. Create a new method `find_pr_template` in the `GitRepo` class in `aider/repo.py` that searches for PR templates in the specified directories (root, docs, .github) and PULL_REQUEST_TEMPLATE subdirectories.
   - Files to edit: `aider/repo.py`

2. Implement logic in the `find_pr_template` method to return the path to a single template if only one is found, or a list of template paths if multiple are found in a PULL_REQUEST_TEMPLATE directory.
   - Files to edit: `aider/repo.py`

3. Create a new method `select_pr_template` in the `GitRepo` class that uses an LLM call to select the appropriate template when multiple templates are found.
   - Files to edit: `aider/repo.py`

4. Modify the `raise_pr` method in the `GitRepo` class to use the PR template content when available, by calling the new `find_pr_template` and `select_pr_template` methods.
   - Files to edit: `aider/repo.py`

5. Update the `cmd_raise_pr` method in the `Commands` class in `aider/commands.py` to handle the PR template functionality by passing the appropriate parameters to the `raise_pr` method.
   - Files to edit: `aider/commands.py`

6. Add a test case in `tests/basic/test_repo.py` to verify that the `find_pr_template` method correctly identifies PR templates in the root directory.
   - Files to edit: `tests/basic/test_repo.py`

7. Add a test case in `tests/basic/test_repo.py` to verify that the `find_pr_template` method correctly identifies PR templates in the docs directory.
   - Files to edit: `tests/basic/test_repo.py`

8. Add a test case in `tests/basic/test_repo.py` to verify that the `find_pr_template` method correctly identifies PR templates in the .github directory.
   - Files to edit: `tests/basic/test_repo.py`

9. Add a test case in `tests/basic/test_repo.py` to verify that the `find_pr_template` method correctly identifies PR templates in PULL_REQUEST_TEMPLATE subdirectories.
   - Files to edit: `tests/basic/test_repo.py`

10. Add a test case in `tests/basic/test_repo.py` to verify that the `select_pr_template` method correctly selects a template when multiple templates are found.
    - Files to edit: `tests/basic/test_repo.py`

11. Add a test case in `tests/basic/test_commands.py` to verify that the `cmd_raise_pr` method correctly uses the PR template when available.
    - Files to edit: `tests/basic/test_commands.py`

# Warning

- Ensure that the PR template detection logic handles cases where no templates are found gracefully, falling back to the current behavior.
- Be careful with file path handling across different operating systems, especially when dealing with directory separators.
- When implementing the LLM call for template selection, make sure to handle potential API failures or timeouts gracefully.
- The implementation should maintain backward compatibility with the existing PR creation functionality.
- Ensure that the template selection logic is isolated and testable independently from the rest of the system.
- Be mindful of the repository structure when searching for templates, as the root directory might be different from the current working directory.
- Consider case sensitivity when searching for template files, as some file systems are case-insensitive.