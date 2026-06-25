from pipeline_contracts import audit_pipeline, format_audit


def main():
    audit = audit_pipeline()
    print()
    print(format_audit(audit))
    print()


if __name__ == "__main__":
    main()
