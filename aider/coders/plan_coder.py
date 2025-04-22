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

    def generate_initial_plan(self, ticket_content):
        message = (
            "Please create an initial implementation plan for this JIRA"
            f" ticket:\n\n{ticket_content}"
        )
        self.run_one(message, preproc=False)
        return self.partial_response_content

    def generate_final_plan(self, ticket_content, initial_plan, affected_files):
        # Include file content for context
        file_contents = ""
        for file in affected_files:
            content = self.io.read_text(self.abs_root_path(file))
            if content:
                file_contents += f"\n\n{file}\n```\n{content}\n```"

        message = (
            "Please create a detailed implementation plan for this JIRA"
            f" ticket:\n\n{ticket_content}\n\nInitial plan:\n{initial_plan}\n\nThe following files"
            f" will need to be modified:\n{', '.join(affected_files)}\n\nHere are the contents of"
            f" these files for reference:{file_contents}\n\nPlease provide a comprehensive"
            " implementation plan with specific changes needed for each file."
        )

        self.init_before_message()
        list(self.send_message(message))  # Consume the generator
        return self.partial_response_content

    def identify_affected_files(self, initial_plan):
        # Create a temporary instance of ContextCoder
        context_coder = ContextCoder(
            self.main_model,
            self.io,
            repo=self.repo,
            map_tokens=self.repo_map.max_map_tokens if self.repo_map else 1024,
            verbose=self.verbose,
        )

        # Use the context_coder to identify relevant files
        message = (
            "Based on the implementation plan below, identify all files that will need to be"
            " modified or created to implement this plan. List only the file paths, one per"
            " line:\n\n"
            + initial_plan
        )

        # Run the context_coder with our message
        context_coder.run_one(message, preproc=False)

        # After running, the context_coder will have identified files in its abs_fnames set
        # We need to convert these to relative paths
        identified_files = [
            context_coder.get_rel_fname(fname) for fname in context_coder.abs_fnames
        ]

        return identified_files
