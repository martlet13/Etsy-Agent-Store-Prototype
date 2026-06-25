from api_connector_manager import check_all_connectors, format_connector_check


def main():
    check = check_all_connectors()
    print()
    print(format_connector_check(check))
    print()


if __name__ == "__main__":
    main()
