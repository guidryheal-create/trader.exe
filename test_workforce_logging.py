        

from camel.tasks import Task
from core.camel_runtime.societies import TradingWorkforceSociety
import asyncio

async def test_workforce_trigger():
    society = TradingWorkforceSociety()
    workforce = await society.build()
    """
    class Task(
        *,
        content: str,
        id: str = lambda : str(uuid.uuid4()),
        state: TaskState = TaskState.FAILED,
        type: str | None = None,
        parent: Task | None = None,
        subtasks: List[Task] = [],
        result: str | None = "",
        failure_count: int = 0,
        assigned_worker_id: str | None = None,
        dependencies: List[Task] = [],
        additional_info: Dict[str, Any] | None = None,
    )
    Task is specific assignment that can be passed to a agent.

    Attributes
    content : str
    string content for task.

    id : str
    An unique string identifier for the task. This should ideally be provided by the provider/model which created the task. (default: uuid.uuid4())

    state : TaskState
    The state which should be OPEN, RUNNING, DONE or DELETED. (default: TaskState.FAILED)

    type : Optional[str]
    task type. (default: None)

    parent : Optional[Task]
    The parent task, None for root task. (default: None)

    subtasks : List[Task]
    The childrent sub-tasks for the task. (default: [])

    result : Optional[str]
    The answer for the task. (default: "")

    failure_count : int
    The failure count for the task. (default: 0)

    assigned_worker_id : Optional[str]
    The ID of the worker assigned to this task. (default: None)

    dependencies : List[Task]
    The dependencies for the task. (default: [])

    additional_info : Optional[Dict[str, Any]]
    Additional information for the task. (default: None)
    """

    task = Task(
                content=(
                    "You are a Polymarket assistant. Answer the user briefly and clearly.\n\n"
                )
            )
    print(workforce.get_workforce_log_tree()) # Returns an ASCII tree representation of the task hierarchy and worker status.
    print(workforce.get_pending_tasks()) # Get current pending tasks for human review.
    print(workforce.get_completed_tasks()) # Get completed tasks.
    print(workforce.get_workforce_kpis()) # Returns a dictionary of key performance indicators.
    # workforce.to_mcp() 
    """
            def to_mcp(
                name: str = "CAMEL-Workforce",
                description: str = "A workforce system using the CAM" "multi-agent collaboration.",
                dependencies: List[str] | None = None,
                host: str = "localhost",
                port: int = 8001
            ) -> FastMCP[Any]
            Expose this Workforce as an MCP server.

            Args
            name : str
            Name of the MCP server. (default: CAMEL-Workforce)
    """
    print(workforce.stop_gracefully()) # Request workforce to finish current in-flight work then halt.


if __name__ == "__main__":
    asyncio.run(test_workforce_trigger())