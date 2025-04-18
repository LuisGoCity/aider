## Task outline
- Implement a high level function that uses the existing functionalities to further automate the use of aider. 
- This function will take a path to an .md file containing the plan for a code implementation and autoomatically implement it step by step.

## Some main features
1. `cmd_code_from_plan` function in `aider/commands.py` that takes the path to a .md file as arg.
2. This function then:
   1. Runs existing `cmd_add` to add the file to context.
   2. Runs existing `cmd_ask` to figure out how many steps are in the plan.
   3. Parses result to an integer.
   4. iterates from 1 to number of steps using cmd_code asking it to implement step `n` of the plan