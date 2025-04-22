import json

from .base_coder import Coder
from .context_coder import ContextCoder
from .plan_prompts import PlanPrompts


class PlanCoder(Coder):
    """Generate an implementation plan from a file containing feature specifications."""

    edit_format = "plan"
    gpt_prompts = PlanPrompts()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.repo_map:
            return

        self.repo_map.refresh = "always"
        self.repo_map.max_map_tokens *= self.repo_map.map_mul_no_files
        self.repo_map.map_mul_no_files = 1.0

    def run(self, ticket_content):
        initial_plan = self.generate_initial_plan(ticket_content)

        files_to_edit = self.identify_affected_files(initial_plan)
        final_plan = self.generate_final_plan(ticket_content, initial_plan, files_to_edit)

        self.io.tool_output(
            f"From the ticket provided, here is how I would implement this feature:\n{final_plan}"
        )
        return final_plan

    def generate_initial_plan(self, ticket_content):
        message = f"Please create an implementation plan for this JIRA ticket:\n\n{ticket_content}"
        self.run_one(message, preproc=False)
        return self.partial_response_content

    def generate_final_plan(self, ticket_content, initial_plan, affected_files):
        # Handle both dictionary and set/list formats of affected_files
        if isinstance(affected_files, dict):
            message = (
                "Please create a more detailed implementation plan for this JIRA"
                f" ticket:\n\n{ticket_content}\n\nInitial plan:\n{initial_plan}\n\nFor each step,"
                " indicate what files will need editing (if any) based on the dictionary of"
                f" identifiedfiles below:\n {json.dumps(affected_files)}"
            )
        else:
            message = (
                "Please create a more detailed implementation plan for this JIRA"
                f" ticket:\n\n{ticket_content}\n\nInitial plan:\n{initial_plan}\n\n"
                f"include a reference to the list of files below:\n {affected_files}."
            )

        self.run_one(message, preproc=False)
        return self.partial_response_content

    def identify_affected_files(self, initial_plan):
        # First, ask the LLM to identify how many steps are in the plan
        message = (
            "How many distinct implementation steps are in this plan? Please respond with just an"
            " integer corresponingto the number of steps:\n\n"
            + initial_plan
        )

        self.run_one(message, preproc=False)
        self.remove_reasoning_content()
        # Extract the number from the response
        try:
            num_steps = int(self.partial_response_content)
            if num_steps <= 0:
                raise ValueError("No steps detected")  # If no steps detected, raise ValueError

            self.io.tool_output(f"Identified {num_steps} implementation steps")

            all_identified_files = {}

            # Make one call per step
            for step_num in range(1, num_steps + 1):
                self.io.tool_output(f"Identifying files for step {step_num} of {num_steps}...")

                all_identified_files[f"Step {step_num}"] = self.files_in_step(
                    initial_plan, step_num
                )

            return all_identified_files
        except (ValueError, TypeError):
            self.io.tool_warning(
                "Could not determine number of steps, returning all files at once."
            )
            message = (
                "Please, detetermine the specific files that would need editing to implement the"
                " plan below:\n\n"
                + initial_plan
            )

            context_coder = self.ask_context_coder(message)
            return {context_coder.get_rel_fname(fname) for fname in context_coder.abs_fnames}

    def files_in_step(self, initial_plan, step_num):
        # Use the context_coder to identify relevant files for this step
        message = (
            f"For step {step_num} of the implementation plan below, identify all files that will"
            " need to be modified or created. List only the file paths, one per"
            f" line:\n\n{initial_plan}"
        )

        context_coder = self.ask_context_coder(message)

        # Add the identified files to our set
        step_files = {context_coder.get_rel_fname(fname) for fname in context_coder.abs_fnames}
        # Clear the context_coder's files for the next step
        context_coder.abs_fnames.clear()
        return list(step_files)

    def ask_context_coder(self, message):
        # Create a temporary instance of ContextCoder
        context_coder = ContextCoder(
            self.main_model,
            self.io,
            repo=self.repo,
            map_tokens=self.repo_map.max_map_tokens if self.repo_map else 1024,
            verbose=self.verbose,
        )
        # Run the context_coder with our message
        context_coder.run_one(message, preproc=False)

        return context_coder
