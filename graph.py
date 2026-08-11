# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, START
# pyrefly: ignore [missing-import]
from langgraph.checkpoint.memory import MemorySaver

from shared.state import SupportState
from shared.logger import log_agent

from agents.intake.node import intake_agent
from agents.planner.node import planner_agent
from agents.orchestration.node import orchestration_agent
from agents.execution.node import execution_agent
from agents.execution_result.node import execution_result_agent
from agents.summarization.node import summarization_agent
from agents.escalation.node import escalation_agent


def build_graph():
    builder = StateGraph(SupportState)

    builder.add_node("intake_agent", log_agent(intake_agent))
    builder.add_node("planner_agent", log_agent(planner_agent))
    builder.add_node("orchestration_agent", log_agent(orchestration_agent))
    builder.add_node("execution_agent", log_agent(execution_agent))
    builder.add_node("execution_result_agent", log_agent(execution_result_agent))
    builder.add_node("summarization_agent", log_agent(summarization_agent))
    builder.add_node("escalation_agent", log_agent(escalation_agent))


    # Fixed agent start
    builder.add_edge(START, "intake_agent")

    return builder.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["execution_agent"]
    )


graph = build_graph()
