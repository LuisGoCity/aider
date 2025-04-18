import os
import re

class PlanExecutor:
    def __init__(self, coder, io):
        self.coder = coder
        self.io = io
        
    def get_step_count(self, plan_path):
        """Ask the LLM to determine how many steps are in the plan."""
        prompt = f"How many steps are in the plan? Please respond with just a number."
        
        # Create a temporary coder to handle this question
        temp_coder = self.coder.clone(
            cur_messages=[],
            done_messages=[]
        )
        
        # Use the ask command to get the step count
        response = temp_coder.run(prompt, with_message=prompt)
        
        # Extract the number from the response
        if response:
            # Look for a number in the response
            match = re.search(r'\b(\d+)\b', response)
            if match:
                return int(match.group(1))
        
        # Default to 0 if we couldn't determine the step count
        return 0
        
    def execute_plan(self, plan_path):
        """Execute each step in the plan."""
        # Get the number of steps in the plan
        step_count = self.get_step_count(plan_path)
        
        if step_count <= 0:
            self.io.tool_error("Could not determine the number of steps in the plan.")
            return
            
        self.io.tool_output(f"Found {step_count} steps in the plan.")
        
        for i in range(1, step_count + 1):
            self.io.tool_output(f"\n[{i}/{step_count}] Executing step {i}")
            
            # Confirm before executing each step
            if i > 1 and not self.io.confirm_ask(f"Continue with step {i}?"):
                self.io.tool_output("Plan execution paused. Use /code-from-plan to resume.")
                return
                
            # Execute the step by sending it to the LLM
            prompt = f"I'm implementing a plan step by step. Please help me with step {i} from the plan. Implement just this step now."
            
            # Use the coder's run method to process this step
            self.coder.run(prompt)
            
        self.io.tool_output("\n✅ Plan execution completed!")
