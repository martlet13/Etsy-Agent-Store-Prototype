from spacecommand_task_manager import run_next_task


def main() -> None:
    result = run_next_task(review=True, archive_on_approved=True)

    print()
    print("# Run Next Task Result")
    print()
    print(result.get("message", ""))

    task = result.get("task")
    if task is None:
        return

    print()
    print(f"Task ID: {task['id']}")
    print(f"Mission: {task['mission_title']}")
    print(f"Title: {task['title']}")
    print(f"Assigned Agent: {task['assigned_agent']}")
    print(f"Status: {task['status']}")
    print(f"Sentinel Verdict: {task.get('sentinel_verdict')}")
    print(f"Archived: {task.get('archived')}")
    print()

    if "agent_output" in result:
        print("## Agent Output")
        print()
        print(result["agent_output"])
        print()

    if "sentinel_output" in result:
        print("## Sentinel Output")
        print()
        print(result["sentinel_output"])
        print()


if __name__ == "__main__":
    main()
