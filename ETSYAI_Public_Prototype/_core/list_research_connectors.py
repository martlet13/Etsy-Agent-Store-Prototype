from research_connector_registry import list_connectors, format_connectors


def main():
    print()
    print(format_connectors(list_connectors()))
    print()


if __name__ == "__main__":
    main()
