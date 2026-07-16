"""
One-time migration: copies existing local JSON data (properties/, history/)
into the Postgres database. Safe to re-run — uses the same upsert logic as
normal saves, so it won't duplicate properties, though it will duplicate
history rows if run twice for the same property.
Run: python3 migrate_to_db.py
"""
import storage as local_storage  # the old local-file storage module
import db_storage


def main():
    db_storage.init_schema()

    properties = local_storage.list_properties()
    if not properties:
        print("No local properties found — nothing to migrate.")
        return

    for slug, profile in properties:
        db_storage.save_profile(slug, profile)
        history = local_storage.load_history(slug)
        for snapshot in history:
            db_storage.save_snapshot(slug, snapshot)
        print(f"Migrated {slug}: profile + {len(history)} history entr{'y' if len(history) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
