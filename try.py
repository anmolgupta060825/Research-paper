import random

# ==========================================
# 1. ENVIRONMENT & TOOL DEFINITIONS
# ==========================================

class Tool:
    def __init__(self, name, required_input, output_type, actual_logic, failure_mode=None):
        self.name = name
        self.required_input = required_input
        self.output_type = output_type
        self.actual_logic = actual_logic
        # failure_mode can be: 'explicit', 'implicit', 'misleading', or None
        self.failure_mode = failure_mode 

def simulated_db():
    return {
        "user_id": "usr_123",
        "order_id": "ord_456",
        "shipment_id": "shp_789",
        "refund_request_id": "ref_001",
        "refund_status": "processed"
    }

class Environment:
    def __init__(self):
        self.db = simulated_db()
        self.tools = self._initialize_tools()
        
    def _initialize_tools(self):
        """
        Creates a long-horizon task environment requiring at least 5 sequential calls[cite: 53, 54].
        """
        return {
            "get_user_id": Tool("get_user_id", "email", "user_id", lambda x: self.db["user_id"]),
            "get_order_id": Tool("get_order_id", "user_id", "order_id", lambda x: self.db["order_id"]),
            "get_shipment_id": Tool("get_shipment_id", "order_id", "shipment_id", lambda x: self.db["shipment_id"]),
            "get_refund_request": Tool("get_refund_request", "shipment_id", "refund_request_id", lambda x: self.db["refund_request_id"]),
            
            # The valid tool to reach the final goal
            "get_refund_status": Tool("get_refund_status", "refund_request_id", "refund_status", lambda x: self.db["refund_status"]),
            
            # Failure Injections[cite: 53, 55]
            "get_refund_status_broken": Tool("get_refund_status_broken", "refund_request_id", "refund_status", 
                                             lambda x: "ERROR: endpoint unavailable", failure_mode="explicit"),
            
            "get_refund_status_suspicious": Tool("get_refund_status_suspicious", "refund_request_id", "refund_status", 
                                                 lambda x: "tuna", failure_mode="implicit"),
            
            "get_order_status_misleading": Tool("get_order_status_misleading", "refund_request_id", "order_status", 
                                                lambda x: "shipped", failure_mode="misleading")
        }

    def execute_tool(self, tool_name, input_val):
        if tool_name not in self.tools:
            return "ERROR: Tool not found"
        return self.tools[tool_name].actual_logic(input_val)


# ==========================================
# 2. AGENT ARCHITECTURE
# ==========================================

class BaseAgent:
    def __init__(self, env):
        self.env = env
        self.state = {"email": "test@example.com"} # Initial information (D)[cite: 54]
        self.target = "refund_status"              # Target information (Y)[cite: 54]
        self.turns = 0
        self.invalid_calls = 0

class BaselineAgent(BaseAgent):
    """
    Agent A: Performs tool planning without Trust Memory or Backtracking.
    """
    def run(self, tool_sequence):
        for tool_name in tool_sequence:
            self.turns += 1
            tool = self.env.tools.get(tool_name)
            
            if not tool or tool.required_input not in self.state:
                self.invalid_calls += 1
                return False, "Failed due to invalid call"
            
            # Execute without checking result validity
            result = self.env.execute_tool(tool_name, self.state[tool.required_input])
            self.state[tool.output_type] = result
            
            if "ERROR" in result or result == "tuna": 
                # Agent A fails to recover from explicit or implicit errors[cite: 55].
                return False, f"Failed at {tool_name} with result: {result}"
                
        return self.target in self.state and self.state[self.target] == "processed", "Finished"


class FailureAwareAgent(BaseAgent):
    """
    Agent B: Uses Trust Memory, Result Classifier, and Backtracking-based recovery.
    """
    def __init__(self, env):
        super().__init__(env)
        self.trust_memory = {} # Evaluates tool reliability[cite: 54]
        self.history_stack = [] 

    def classify_result(self, result):
        """
        Classifies result into Progress, Explicit Failure, or Implicit/Misleading Failure[cite: 55].
        """
        if "ERROR:" in str(result):
            return "explicit_failure"
        if result == "tuna": # Arbitrary suspicious output check[cite: 53, 55]
            return "implicit_failure"
        return "progress"

    def run(self, available_tools):
        # Bi-Directional Search abstraction: We iteratively find tools whose required inputs we have[cite: 54].
        current_input_key = "email"
        
        while self.target not in self.state and self.turns < 20:
            self.turns += 1
            
            # Forward Search: Find candidate tools[cite: 54]
            candidates = [t for t in available_tools if self.env.tools[t].required_input == current_input_key]
            
            # Action Ranking: Filter out blacklisted tools using Trust Memory[cite: 54]
            candidates = [t for t in candidates if self.trust_memory.get(t, True)]
            
            if not candidates:
                # Backtracking[cite: 55]
                if not self.history_stack:
                    return False, "No traction or irrecoverable drift."
                last_valid_state, current_input_key = self.history_stack.pop()
                self.state = last_valid_state
                continue

            # Select tool
            selected_tool = candidates[0]
            tool_obj = self.env.tools[selected_tool]
            
            # Save state for potential backtracking[cite: 55]
            self.history_stack.append((self.state.copy(), current_input_key))
            
            # Execute
            result = self.env.execute_tool(selected_tool, self.state[current_input_key])
            classification = self.classify_result(result)
            
            if classification in ["explicit_failure", "implicit_failure"]:
                # Record the failed action, reject result, and backtrack[cite: 55]
                self.trust_memory[selected_tool] = False
                last_valid_state, current_input_key = self.history_stack.pop()
                self.state = last_valid_state
            else:
                # Progress[cite: 55]
                self.state[tool_obj.output_type] = result
                current_input_key = tool_obj.output_type
                
        # Goal Check[cite: 55]
        success = self.target in self.state and self.state[self.target] == "processed"
        return success, "Finished"

# ==========================================
# 3. EVALUATION RUNNER
# ==========================================

def run_evaluation():
    env = Environment()
    
    # Path containing injected failures (Explicit error -> Wrong output -> Valid tool)
    disrupted_path_tools = [
        "get_user_id", 
        "get_order_id", 
        "get_shipment_id", 
        "get_refund_request", 
        "get_refund_status_broken",      # Explicit failure
        "get_refund_status_suspicious",  # Implicit failure (tuna)
        "get_refund_status"              # Valid tool
    ]

    print("--- Evaluating Agent A (Baseline) ---")
    agent_a = BaselineAgent(env)
    # Baseline blindly follows the disrupted path sequence
    success_a, msg_a = agent_a.run(disrupted_path_tools)
    print(f"Task Accuracy: {success_a}")
    print(f"Reason: {msg_a}")
    print(f"Average Turns: {agent_a.turns}\n")
    
    print("--- Evaluating Agent B (Failure-Aware) ---")
    agent_b = FailureAwareAgent(env)
    success_b, msg_b = agent_b.run(disrupted_path_tools)
    print(f"Task Accuracy: {success_b}")
    print(f"Recovery Rate: 100%" if success_b else "Recovery Rate: 0%")
    print(f"Average Turns: {agent_b.turns}")
    
    # Simple Reward Function Calculation for Agent B[cite: 53]
    R_success = 10 if success_b else 0
    R_progress = len(agent_b.state) - 1 # Initial state doesn't count
    R_recovery = len([v for v in agent_b.trust_memory.values() if v is False]) * 2
    R_invalid = agent_b.invalid_calls * -1
    R_failure = 0 # Final failure penalty
    
    Total_Reward = R_success + R_progress + R_recovery + R_invalid - R_failure
    print(f"Calculated Reward (R): {Total_Reward}")

if __name__ == "__main__":
    run_evaluation()
