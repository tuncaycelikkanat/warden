import sys
import json
import os

# Add the project root to sys.path so we can import core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.monitor import AgentActionMonitor

def main():
    try:
        # Antigravity sends context as JSON on stdin
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"decision": "allow"}))
            return
            
        payload = json.loads(input_data)
        
        # Check if it's a run_command tool call
        tool_call = payload.get("toolCall", {})
        if tool_call.get("name") == "run_command":
            command = tool_call.get("args", {}).get("CommandLine", "")
            
            if command:
                monitor = AgentActionMonitor()
                result = monitor.evaluate_action(command)
                
                if result["requires_confirmation"]:
                    reasons = ", ".join(result["reasons"])
                    print(json.dumps({
                        "decision": "force_ask",
                        "reason": f"WARDEN SECURITY ALERT: Command blocked. Reason: {reasons}"
                    }))
                    return
                    
        # Allow by default if no dangerous patterns match
        print(json.dumps({"decision": "allow"}))
        
    except Exception as e:
        # On error, allow execution but we could log it
        print(json.dumps({"decision": "allow", "reason": f"Hook error: {str(e)}"}))

if __name__ == "__main__":
    main()
