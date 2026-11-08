"""Local profile/CV commands. Document text is displayed only for review/show."""

import sqlite3

from . import storage
from .cli import read_required, read_skills
from .documents import DocumentError, MAX_TEXT_CHARS, extract_document, validate_segments


def safe_display(text):
    """Prevent document text from executing terminal escape/control sequences."""
    return "".join(c if c.isprintable() or c in "\n\t" else f"\\u{ord(c):04x}" for c in str(text))


def confirm(prompt, read, write):
    while True:
        answer = read(prompt + " ").strip().casefold()
        if answer in {"yes", "y"}:
            return True
        if answer in {"no", "n"}:
            return False
        write("Please answer yes/y or no/n.")


def show_segments(segments, write):
    for index, segment in enumerate(segments, 1):
        write(f"\n[{index}: {safe_display(segment.reference)}]")
        write(safe_display(segment.reviewed_text))


def review_document(document, read=input, write=print):
    for warning in document.warnings:
        write("Warning: " + safe_display(warning))
    show_segments(document.segments, write)
    write("Review the text above. Original extraction will be preserved separately from corrections.")
    while True:
        choice = read("Enter a source-unit number to edit, 'done' to finish, or 'cancel': ").strip().lower()
        if choice == "cancel":
            return False
        if choice == "done":
            try:
                validate_segments(document.segments)
            except DocumentError as error:
                write(str(error))
                continue
            show_segments(document.segments, write)
            return confirm("Save this reviewed CV locally? (yes/no)", read, write)
        if not choice.isascii() or not choice.isdecimal() or len(choice) > 6:
            write("Enter a valid source-unit number, done or cancel.")
            continue
        index = int(choice) - 1
        if not 0 <= index < len(document.segments):
            write("That source-unit number does not exist.")
            continue
        write("Enter replacement text; finish with a line containing only /done. Blank text clears the unit.")
        lines = []
        length = 0
        too_long = False
        while True:
            line = read("")
            if line == "/done":
                break
            length += len(line) + 1
            if length > MAX_TEXT_CHARS:
                too_long = True
            if not too_long:
                lines.append(line)
        if too_long:
            write("Correction exceeds 200,000 characters; previous text retained.")
        else:
            document.segments[index].reviewed_text = "\n".join(lines)


def run_command(args, read=input, write=print):
    try:
        if args.command == "profile-create":
            name = read_required("Profile name: ", read, write)
            skills = read_skills(read, write)
            write("Profile: " + safe_display(name))
            write("Skills: " + safe_display(", ".join(skills) or "None"))
            if not confirm("Save this profile locally? (yes/no)", read, write):
                write("Cancelled; no profile saved.")
                return 0
            with storage.database(args.database) as connection:
                profile_id = storage.create_profile(connection, name, skills)
            write(f"Profile saved with ID {profile_id}.")
        elif args.command == "cv-import":
            with storage.database(args.database) as connection:
                profile = storage.get_profile(connection, args.profile)
            write("Importing for profile: " + safe_display(profile["name"]))
            document = extract_document(args.path)
            title = read("CV title (Enter to use filename): ").strip() or document.filename
            if not title or len(title) > 200:
                raise storage.StorageError("CV title must contain 1 to 200 characters.")
            write("CV title: " + safe_display(title))
            if not review_document(document, read, write):
                write("Cancelled; no CV content saved.")
                return 0
            with storage.database(args.database) as connection:
                cv_id = storage.save_cv(connection, args.profile, title, document)
            write(f"Reviewed CV saved with ID {cv_id}.")
        elif args.command == "cv-delete":
            with storage.database(args.database) as connection:
                storage.get_cv(connection, args.id)
            if not confirm(f"Delete CV {args.id} and all its stored text? (yes/no)", read, write):
                write("Cancelled; no CV deleted.")
                return 0
            with storage.database(args.database) as connection:
                storage.delete_cv(connection, args.id)
            write("CV and its stored content deleted. The original document was not changed.")
        else:
            with storage.database(args.database) as connection:
                if args.command == "profile-list":
                    rows = storage.list_profiles(connection)
                    for row in rows:
                        write(f"{row['id']}: {safe_display(row['name'])}")
                    if not rows:
                        write("No profiles saved.")
                elif args.command == "cv-list":
                    rows = storage.list_cvs(connection, args.profile)
                    for row in rows:
                        write(f"{row['id']}: {safe_display(row['title'])} ({row['file_type']}, profile {row['profile_id']})")
                    if not rows:
                        write("No CVs saved.")
                elif args.command == "cv-show":
                    cv = storage.get_cv(connection, args.id)
                    write(f"CV {cv['id']}: {safe_display(cv['title'])}")
                    write("Original extracted text" if args.source else "Reviewed text")
                    for segment in cv["segments"]:
                        write(f"\n[{safe_display(segment['reference'])}]")
                        write(safe_display(segment["source_text" if args.source else "reviewed_text"]))
        return 0
    except (DocumentError, storage.StorageError) as error:
        write(str(error))
    except (OSError, sqlite3.Error):
        write("Local database operation failed. Check the database path, permissions and available space.")
    return 1
