from forge_image_kernel import audit_image_assets, format_image_audit


def main():
    audit = audit_image_assets()
    print()
    print(format_image_audit(audit))
    print()


if __name__ == "__main__":
    main()
