import argparse
from spacecommand_task_manager import run_next_task, status_summary, load_tasks, load_missions


HARD_STOP_STATUSES = {
    "human_approval_required",
    "failed",
    "rejected",
    "review_unknown",
}

ATTENTION_STATUSES = {
    "pending_revision",
    "human_approval_required",
    "failed",
    "rejected",
    "review_unknown",
}


def has_blocking_task() -> bool:
    tasks = load_tasks()
    return any(task.get("status") in HARD_STOP_STATUSES for task in tasks)


def has_pending_task() -> bool:
    tasks = load_tasks()
    return any(task.get("status") in {"pending", "pending_revision"} for task in tasks)


def active_mission_count() -> int:
    missions = load_missions()
    return sum(1 for mission in missions if mission.get("status") == "active")


def main():
    parser = argparse.ArgumentParser(description="Run a safe local SpaceCommand mission cycle.")
    parser.add_argument("--max-tasks", type=int, default=3, help="Maximum tasks to run in one cycle.")
    parser.add_argument("--stop-on-review", action="store_true", help="Stop after any Sentinel-reviewed task.")
    args = parser.parse_args()

    print()
    print("# SpaceCommand Mission Cycle")
    print()
    print(f"Max tasks this cycle: {args.max_tasks}")
    print(f"Active missions: {active_mission_count()}")
    print()

    completed_this_cycle = 0

    for index in range(args.max_tasks):
        if has_blocking_task():
            print("Cycle stopped: blocking task exists.")
            print("Reason: human_approval_required, failed, rejected, or review_unknown task detected.")
            print()
            break

        if not has_pending_task():
            print("Cycle stopped: no pending tasks.")
            print()
            break

        print(f"## Cycle Step {index + 1}")
        print()

        result = run_next_task(review=True, archive_on_approved=True)
        task = result.get("task")

        if task is None:
            print(result.get("message", "No task returned."))
            print()
            break

        completed_this_cycle += 1

        print(f"Task ID: {task.get('id')}")
        print(f"Title: {task.get('title')}")
        print(f"Agent: {task.get('assigned_agent')}")
        print(f"Status: {task.get('status')}")
        print(f"Sentinel Verdict: {task.get('sentinel_verdict')}")
        print()

        if task.get("status") in ATTENTION_STATUSES:
            print("Cycle stopped: latest task needs attention.")
            print()
            break

        if args.stop_on_review and task.get("requires_review"):
            print("Cycle stopped: --stop-on-review was enabled.")
            print()
            break

    print("# Cycle Summary")
    print()
    print(f"Tasks completed this cycle: {completed_this_cycle}")
    print()
    print(status_summary())


if __name__ == "__main__":
    main()

