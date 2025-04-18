import os
import re
from dataclasses import dataclass

@dataclass
class PlanStep:
    title: str
    description: str
    index: int


class PlanExecutor:
    def __init__(self, coder, io):
        self.coder = coder
        self.io = io
        
    def parse_plan(self, plan_path):
        """Parse a markdown file into discrete steps."""
        with open(plan_path, 'r', encoding=self.io.encoding, errors="replace") as f:
            content = f.read()
            
        # First, add the file to context
        abs_path = os.path.abspath(plan_path)
        rel_path = self.coder.get_rel_fname(abs_path)
        self.coder.add_rel_fname(rel_path)
        self.io.tool_output(f"Added plan file to context: {rel_path}")
        
        # Parse steps (assuming steps are marked by ## Step X: or similar)
        steps = []
        step_pattern = r'##\s*Step\s*(\d+):\s*(.*?)(?=##|\Z)'
        matches = re.finditer(step_pattern, content, re.DOTALL)
        
        for match in matches:
            index = int(match.group(1))
            full_content = match.group(0)
            
            # Extract title (first line after the step header)
            title_match = re.search(r'##\s*Step\s*\d+:\s*(.*?)(?=\n|\Z)', full_content)
            title = title_match.group(1).strip() if title_match else "Untitled Step"
            
            # Extract description (everything after the title)
            description = full_content[title_match.end():].strip() if title_match else full_content
            
            steps.append(PlanStep(title=title, description=description, index=index))
            
        return sorted(steps, key=lambda s: s.index)
        
    def execute_plan(self, plan_path):
        """Execute each step in the plan."""
        steps = self.parse_plan(plan_path)
        
        if not steps:
            self.io.tool_error("No steps found in the plan file.")
            return
            
        self.io.tool_output(f"Found {len(steps)} steps in the plan.")
        
        for i, step in enumerate(steps):
            self.io.tool_output(f"\n[{i+1}/{len(steps)}] Executing: {step.title}")
            
            # Confirm before executing each step
            if i > 0 and not self.io.confirm_ask(f"Continue with step {i+1}: {step.title}?"):
                self.io.tool_output("Plan execution paused. Use /code-from-plan to resume.")
                return
                
            # Execute the step by sending it to the LLM
            prompt = f"I'm implementing a plan step by step. Please help me with step {step.index}:\n\n{step.title}\n\n{step.description}\n\nImplement just this step now."
            
            # Use the coder's run method to process this step
            self.coder.run(prompt)
            
        self.io.tool_output("\nPlan execution completed!")
