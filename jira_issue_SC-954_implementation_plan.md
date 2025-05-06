# Implementation Plan for Auto-Confirm Context Manager

## Task Outline
Create a context manager approach to refactor the auto-confirm functionality in the Commands class, specifically for the `cmd_code_from_plan` and `cmd_clean_code` methods, which currently bypass the `confirm_ask` method by setting a temporary method for more autonomy.

## Steps

1. Create a private context manager class `_AutoConfirmContext` inside the Commands class in `aider/commands.py` that will handle setting `self.io.confirm_ask` to `self.io.auto_confirm_ask` in `__enter__` and restoring the original method in `__exit__`.

2. Create a private method `_with_auto_confirm` in the Commands class in `aider/commands.py` that returns an instance of the `_AutoConfirmContext` context manager.

3. Modify `cmd_code_from_plan` method in `aider/commands.py` to use the new `_with_auto_confirm` context manager instead of manually swapping the confirm_ask method.

4. Modify `cmd_clean_code` method in `aider/commands.py` to use the new `_with_auto_confirm` context manager instead of manually swapping the confirm_ask method.

5. Update the `_from_plan_exist_strategy` method in `aider/commands.py` to remove the `original_confirmation_ask_method` parameter since it will no longer be needed.

6. Create a test for the new `_with_auto_confirm` context manager in `tests/basic/test_commands.py` to ensure it properly sets and restores the confirm_ask method.

7. Update the test `test_cmd_code_from_plan_positive` in `tests/basic/test_commands.py` to reflect the new implementation without manually swapping confirm_ask methods.

## Warning
- Ensure that the context manager properly handles exceptions to guarantee that the original confirm_ask method is always restored, even if an error occurs during execution.
- Be careful not to change the actual behavior of the auto-confirm functionality, as the ticket only requires refactoring the implementation, not changing its behavior.
- The context manager should be implemented as a method that returns a context manager object, not as a decorator, to maintain compatibility with the existing code structure.
- Make sure the `_from_plan_exist_strategy` method works correctly without the original_confirm_ask parameter, as this change could affect how the method functions.