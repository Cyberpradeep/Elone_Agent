import sys
from loguru import logger

logger.remove()
logger.add(sys.stderr, format="<cyan>{time:HH:mm:ss}</cyan> | <level>{level}</level> | {message}")

def log_agent(func):
    """
    Decorator to wrap any agent node. Automatically logs when the agent 
    starts, finishes, and safely dumps its state updates and routing.
    """
    def wrapper(state):
        agent_name = func.__name__
        logger.info(f"▶▶▶ [START] {agent_name}")
        
        try:
            result = func(state)
            
            goto = getattr(result, "goto", "Unknown")
            updates = getattr(result, "update", {})
            
            import json
            pretty_updates = json.dumps(updates, indent=4, default=str)
            
            logger.info(f"◀◀◀ [END] {agent_name} | Routing to: {goto}\nUpdates:\n{pretty_updates}\n")
            return result
            
        except Exception as e:
            logger.error(f"✖✖✖ [ERROR] {agent_name} crashed: {str(e)}\n")
            raise
            
    return wrapper
