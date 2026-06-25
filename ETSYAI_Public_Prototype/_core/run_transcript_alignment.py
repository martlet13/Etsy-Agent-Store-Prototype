from transcript_alignment import run_alignment


def main() -> None:
    report = run_alignment()
    print("V10 Transcript Alignment Adapter")
    print(f"Status: {report['status']}")
    print(f"Tabs built: {', '.join(report['tabs'])}")
    print(f"Needs user action: {report['needs_user_action']}")
    if report["ensured_optional_files"]:
        print("Created or seeded optional files:")
        for file_name in report["ensured_optional_files"]:
            print(f"- _spacecommand_state/{file_name}")
    print("Updated files:")
    for file_name in report["updated_files"]:
        print(f"- _spacecommand_state/{file_name}")


if __name__ == "__main__":
    main()
