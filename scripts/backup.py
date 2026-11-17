import argparse
from pathlib import Path

from app.config import load_settings
from app.services.backups import create_backup, restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a private backup or restore into a new directory."
    )
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.restore:
        if not args.destination:
            parser.error("--restore requires --destination pointing to a new directory")
        restore_backup(args.restore, args.destination)
        print("Restore completed. Reconcile deletion receipts before allowing access.")
    else:
        print(create_backup(load_settings()))


if __name__ == "__main__":
    main()
