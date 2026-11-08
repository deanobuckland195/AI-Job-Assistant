"""Reviewable CV analysis, optional consent-gated assistance and explicit export."""

import sqlite3

from . import storage
from .cv_analysis import AnalysisError, analyse_cv
from .cv_analysis_report import format_cv_analysis, save_cv_report
from .cv_cli import confirm, safe_display


def run_analysis(args, read=input, write=print):
    try:
        with storage.database(args.database) as connection:
            cv = storage.get_cv(connection, args.id)
        analysis = analyse_cv(cv)
        report_text = format_cv_analysis(analysis)
        write(report_text)
        if args.openai:
            from .openai_analysis import prepare_request, request_assistance
            try:
                prepare_request(cv, args.model)  # Validate limits before asking to transmit.
                write("OpenAI mode sends the reviewed CV text (including any personal data it contains) to api.openai.com.")
                write("This may incur API charges, even if the response is rejected or fails. No automatic retries.")
                write("Limits: 12,000 characters / 200 units, 1,800 output tokens, one request, 30-second socket timeout.")
                write("store=false is used, but provider abuse-monitoring retention may still apply. This is not zero retention.")
                write("Model: " + safe_display(args.model) + ". Check current pricing and account spend limits before proceeding.")
                write("Only curated, evidence-linked suggestions are accepted; model output cannot add CV facts.")
                if read("Type SEND to consent to this one paid external request, or Enter to stay offline: ") == "SEND":
                    analysis.suggestions.extend(request_assistance(cv, args.model, consent=True))
                    analysis.notes.append("OpenAI-selected suggestions passed structural/citation checks; relevance still requires your review.")
                else:
                    analysis.notes.append("OpenAI request declined; this report remains fully offline.")
            except AnalysisError as error:
                analysis.notes.append(str(error))
            report_text = format_cv_analysis(analysis)
            write(report_text)
        if args.output:
            write("This report includes personal CV excerpts. Save it in a private local folder such as local_data/.")
            if confirm(f"Save this reviewed report to {safe_display(args.output)}? (yes/no)", read, write):
                try:
                    save_cv_report(report_text, args.output)
                except FileExistsError:
                    write("Report not saved: that path already exists. Choose a new output filename.")
                    return 1
                except OSError:
                    write("Report could not be saved. Check permissions, available space and filesystem support for atomic links.")
                    return 1
                write("CV analysis report saved locally.")
            else:
                write("Report not saved.")
        return 0
    except (AnalysisError, storage.StorageError) as error:
        write(str(error))
    except (OSError, sqlite3.Error):
        write("Could not read the local CV database. Check the path and permissions.")
    return 1
