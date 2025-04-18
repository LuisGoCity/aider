## Task outline
- There have been recent changes to the `aider/commands.py` file, but no tests have been written for them.
- Your task is to extend the `tests/basic/test_commands.py` to include the new tests.

## Steps
1. Write a test for all positive outcomes in the `cmd_code_from_plan` function in `aider/commands.py`.
2. Write a test for error handling in the `cmd_code_from_plan` function in `aider/commands.py`.
3. Write a test for all positive outcomes in the `completions_raw_code_from_plan` function in `aider/commands.py`.
4. Write a test for error handling outcomes in the `completions_raw_code_from_plan` function in `aider/commands.py`.
5. Write a test for the `_run_new_coder` function in `aider/commands.py`.
6. Write a test for the `_from_plan_exist_strategy` function in `aider/commands.py`.

## Warnings
- Each test must be written beneath the last test in the file, make in it easier to review.
- Make sure each test covers all edge cases of each function.
- Follow the coding style of the file you're editing.
- Avoid updating this filing informing on your progress.
