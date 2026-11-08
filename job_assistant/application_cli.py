"""Application and stored-comparison commands, with review before mutations."""

import json
import sqlite3
from pathlib import Path

from . import applications as apps, comparison_records as comparisons, storage
from .application_export import export_applications
from .cv_analysis import AnalysisError
from .cv_analysis_report import save_cv_report
from .cv_cli import confirm, safe_display
from .migrations import STATUSES


def register_commands(commands):
    create = commands.add_parser("application-create", help="Review and save a local job application")
    create.add_argument("--company", required=True)
    create.add_argument("--role", required=True)
    add_fields(create, create=True)
    update = commands.add_parser("application-update", help="Review changes and record any status transition")
    update.add_argument("id", type=int)
    update.add_argument("--company")
    update.add_argument("--role")
    add_fields(update)
    showing = commands.add_parser("application-show", help="Show an application, links and status history")
    showing.add_argument("id", type=int)
    deletion = commands.add_parser("application-delete", help="Confirm deletion of an application and its status history")
    deletion.add_argument("id", type=int)
    listing = commands.add_parser("application-list", help="List/filter local applications")
    add_filters(listing)
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)
    export = commands.add_parser("application-export", help="Confirm a private JSON export without CV contents")
    add_filters(export)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--include-notes", action="store_true")
    export.add_argument("--include-history", action="store_true")
    comp_list = commands.add_parser("comparison-list", help="List explicitly stored comparison metadata")
    comp_list.add_argument("--limit", type=int, default=100)
    comp_list.add_argument("--offset", type=int, default=0)
    for name in ("comparison-show", "comparison-delete"):
        parser = commands.add_parser(name, help="Show/delete stored comparison metadata (no source excerpts)")
        parser.add_argument("id", type=int)


def add_fields(parser, create=False):
    parser.add_argument("--job-url")
    parser.add_argument("--application-date", help="YYYY-MM-DD; omitted means unknown, empty string clears on update")
    parser.add_argument("--status", choices=STATUSES, default="saved" if create else None)
    parser.add_argument("--deadline", help="YYYY-MM-DD; past dates allowed for historical records")
    parser.add_argument("--notes")
    parser.add_argument("--next-action")
    parser.add_argument("--follow-up-date", help="Optional YYYY-MM-DD date for the next action")
    completion = parser.add_mutually_exclusive_group()
    completion.add_argument("--complete-action", dest="action_completed", action="store_true")
    completion.add_argument("--reopen-action", dest="action_completed", action="store_false")
    parser.set_defaults(action_completed=False if create else None)
    parser.add_argument("--cv", type=int, help="Approved CV ID")
    parser.add_argument("--comparison", type=int, help="Stored comparison ID; automatically links its approved CV version")
    if not create:
        parser.add_argument("--clear-links", action="store_true", help="Remove both CV and comparison links/snapshots")


def add_filters(parser):
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--company", help="Literal substring; no wildcard expansion")
    parser.add_argument("--role", help="Literal substring")
    parser.add_argument("--deadline-before", help="Inclusive YYYY-MM-DD")
    parser.add_argument("--deadline-after", help="Inclusive YYYY-MM-DD")
    parser.add_argument("--overdue", action="store_true", help="Saved applications with a deadline before today")


def filters(args):
    return {key: getattr(args, key, None) for key in ("status", "company", "role", "deadline_before", "deadline_after", "overdue")}


def format_application(record):
    lines = [f"=== Application {record.get('id', '(new)')} ==="]
    for key in apps.FIELDS:
        value = record.get(key)
        lines.append(f"{key.replace('_', ' ').title()}: {safe_display(value) if value not in (None, '') else '(not recorded)'}")
    if record.get("cv_original_id"):
        lines.extend([f"CV version: original ID {record['cv_original_id']}; live link {record.get('cv_id') or '(deleted/detached)'}",
                      f"CV approved: {safe_display(record.get('cv_reviewed_at'))}", f"Reviewed CV digest: {safe_display(record.get('cv_digest'))}"])
    if record.get("comparison_original_id"):
        lines.append(f"Comparison: original ID {record['comparison_original_id']}; live link {record.get('comparison_id') or '(deleted/detached)'}")
    if "revision" in record:
        lines.append(f"Revision: {record['revision']}; updated: {safe_display(record['updated_at'])}")
    lines.extend("Note: " + note for note in apps.date_notes(record))
    if "history" in record:
        lines.append("Status history (UTC; insertion order):")
        for event in record["history"]:
            lines.append(f"  {safe_display(event['changed_at'])}: {event['from_status'] or '(created)'} -> {event['to_status']}")
    return "\n".join(lines)


def read_link_selection(args):
    if getattr(args, "clear_links", False):
        if args.cv is not None or args.comparison is not None:
            raise apps.ApplicationError("Use --clear-links alone, without --cv or --comparison.")
        return {}
    if args.cv is not None or args.comparison is not None:
        return {"cv_id": args.cv, "comparison_id": args.comparison}
    return None


def run_command(args, read=input, write=print):
    try:
        if args.command == "application-create":
            values = apps.validate_fields({key: getattr(args, key, None) for key in apps.FIELDS})
            selection = {"cv_id": args.cv, "comparison_id": args.comparison}
            with storage.database(args.database) as connection:
                links = apps.resolve_links(connection, **selection)
            write(format_application({**values, **links}))
            if confirm("Save this application locally? (yes/no)", read, write):
                with storage.database(args.database) as connection:
                    app_id = apps.create_application(connection, **values, **selection, expected_links=links)
                write(f"Application saved with ID {app_id}.")
            else:
                write("Cancelled; no application saved.")
        elif args.command == "application-update":
            changes = {key: getattr(args, key) for key in apps.FIELDS if getattr(args, key, None) is not None}
            selection = read_link_selection(args)
            if not changes and selection is None:
                raise apps.ApplicationError("No changes requested. Supply fields to update or --clear-links.")
            with storage.database(args.database) as connection:
                current = apps.get_application(connection, args.id)
                preview = {**current, **apps.prepare_update(current, changes)}
                new_links = apps.resolve_links(connection, **selection) if selection is not None else None
            if new_links is not None:
                preview.update(new_links)
                write("A link update replaces both links. Supply both IDs together to retain both, or link a stored comparison to use its CV version.")
            write("Proposed application (history below is the existing history):")
            write(format_application(preview))
            if confirm("Apply these changes locally? (yes/no)", read, write):
                with storage.database(args.database) as connection:
                    changed = apps.update_application(connection, args.id, changes, links=selection,
                                                      expected_revision=current["revision"], expected_links=new_links)
                write("Application updated; any status change was recorded." if changed else "No values changed; no duplicate history event added.")
            else:
                write("Cancelled; no changes saved.")
        elif args.command == "application-delete":
            with storage.database(args.database) as connection:
                current = apps.get_application(connection, args.id)
            write(format_application(current))
            if confirm("Delete this application and all its status history? CVs/comparisons/reports are retained. (yes/no)", read, write):
                with storage.database(args.database) as connection:
                    apps.delete_application(connection, args.id, expected_revision=current["revision"])
                write("Application and its status history deleted.")
            else:
                write("Cancelled; nothing deleted.")
        elif args.command == "application-export":
            with storage.database(args.database) as connection:
                text = export_applications(connection, include_notes=args.include_notes, include_history=args.include_history, **filters(args))
            count = len(json.loads(text)["applications"])
            write(f"Export contains {count} applications, entered URLs/next actions and link IDs; no CV/comparison excerpts. Notes included: {args.include_notes}; history included: {args.include_history}.")
            if confirm(f"Save private JSON export to {safe_display(args.output)}? (yes/no)", read, write):
                save_cv_report(text, args.output)
                write("Application export saved locally.")
            else:
                write("Cancelled; no export saved.")
        else:
            with storage.database(args.database) as connection:
                if args.command == "application-show":
                    write(format_application(apps.get_application(connection, args.id)))
                elif args.command == "application-list":
                    rows = apps.list_applications(connection, limit=args.limit, offset=args.offset, **filters(args))
                    for row in rows:
                        write(f"{row['id']}: {safe_display(row['company'])} | {safe_display(row['role'])} | {row['status']} | deadline {row['deadline'] or '(unknown)'}")
                    write(f"Listed {len(rows)} application(s); limit {args.limit}, offset {args.offset}.")
                elif args.command == "comparison-list":
                    rows = comparisons.list_comparisons(connection, args.limit, args.offset)
                    for row in rows:
                        write(f"{row['id']}: CV version ID {row['cv_original_id']} | {safe_display(row['created_at'])}")
                    write(f"Listed {len(rows)} comparison(s).")
                elif args.command == "comparison-show":
                    write(json.dumps(comparisons.get_comparison(connection, args.id), ensure_ascii=True, indent=2))
                elif args.command == "comparison-delete":
                    metadata = comparisons.get_comparison(connection, args.id)
                    write(f"Stored comparison {metadata['id']}; CV version ID {metadata['cv_original_id']}.")
                    if confirm("Delete comparison metadata? Applications retain provenance but lose the live link. (yes/no)", read, write):
                        comparisons.delete_comparison(connection, args.id)
                        write("Comparison metadata deleted; applications, CVs and report files retained.")
                    else:
                        write("Cancelled; nothing deleted.")
        return 0
    except (apps.ApplicationError, storage.StorageError, AnalysisError) as error:
        write(str(error))
    except FileExistsError:
        write("Output path already exists; nothing overwritten. Choose a new filename.")
    except (OSError, sqlite3.Error):
        write("Local application operation failed. Check the path, permissions, available space or database lock; no incomplete write was committed.")
    return 1
