"""Explicit offline job comparison; existing job/CV flows remain separate."""

import sqlite3

from . import storage
from .cv_analysis import AnalysisError
from .cv_analysis_report import save_cv_report
from .cv_cli import confirm, safe_display
from .documents import DocumentError
from .job_matching import compare_job
from .job_report import format_comparison
from .job_requirements import JobError, import_job, read_job_entry


def run_comparison(args, read=input, write=print):
    try:
        with storage.database(args.database) as connection:
            cv = storage.get_cv(connection, args.id)
        if args.job_file:
            job, warnings = import_job(args.job_file)
        else:
            job, warnings = read_job_entry(read, write), []
        result = compare_job(cv, job, warnings)
        store_failed = False
        report = format_comparison(result)
        write(report)
        if getattr(args, "openai", False):
            from .openai_job_matching import estimate_cost, prepare_request, request_matching
            result.ai_attempted = True
            result.ai_model = getattr(args, "model", None) or "(not selected)"
            try:
                data = prepare_request(cv, job, result, getattr(args, "model", None))
                input_rate = getattr(args, "input_usd_per_million", None)
                output_rate = getattr(args, "output_usd_per_million", None)
                budget = getattr(args, "max_estimated_usd", "0.25")
                estimate = estimate_cost(data, input_rate, output_rate, budget)
                result.ai_notes.append(f"Pre-request estimate: USD {estimate.usd:.8f}, using supplied rates USD {estimate.input_rate}/{estimate.output_rate} per million input/output tokens; not a billing guarantee.")
                write("AI job matching sends approved reviewed CV text and job text, including personal/confidential data, to api.openai.com.")
                write("Data is not anonymised. store=false is used; provider abuse-monitoring retention may still apply.")
                write(f"Model: {safe_display(result.ai_model)}. Supplied rates: USD {estimate.input_rate}/million input, USD {estimate.output_rate}/million output tokens.")
                write(f"Estimated conservative cost: USD {estimate.usd:.8f}; input proxy={estimate.input_token_proxy} tokens, output limit=2400 tokens; estimated budget=USD {estimate.budget}.")
                write("The input proxy uses encoded bytes plus 1,024 framing tokens, not exact tokenization. This is not a guaranteed bill or provider-enforced spending cap.")
                write("Verify model pricing/account limits. Failed or rejected responses may still be charged.")
                write("Limits: 12,000 CV + 8,000 job characters, 96,000 request bytes, 65,536 response bytes, 12 interpretations, one request, 30-second socket timeout. No retries or tools.")
                if read("Type SEND to authorise this one external request, or Enter to keep offline results: ") == "SEND":
                    result.ai_results = request_matching(cv, job, result, result.ai_model, input_rate=input_rate,
                                                        output_rate=output_rate, max_usd=budget, consent=True)
                    result.ai_notes.append("One AI request processed. Only locally validated interpretations are shown; offline conclusions were not replaced.")
                else:
                    result.ai_notes.append("AI request declined. Offline comparison retained; no data sent.")
            except AnalysisError as error:
                result.ai_notes.append("AI assistance unavailable: " + str(error))
            report = format_comparison(result)
            write(report)
        if getattr(args, "store", False):
            write("Store comparison provenance/counts locally for application links? No CV/job excerpts or full report will be stored.")
            if confirm("Store comparison metadata? (yes/no)", read, write):
                try:
                    from .comparison_records import save_comparison
                    with storage.database(args.database) as connection:
                        comparison_id = save_comparison(connection, result)
                    write(f"Comparison metadata saved with ID {comparison_id}.")
                except (OSError, sqlite3.Error, ValueError):
                    store_failed = True
                    write("Comparison metadata could not be stored; no incomplete metadata was committed. The displayed report remains available.")
            else:
                write("Comparison metadata not stored.")
        if args.output:
            write("This comparison contains personal CV excerpts. Keep exports private, preferably under local_data/.")
            if confirm(f"Save the displayed comparison to {safe_display(args.output)}? (yes/no)", read, write):
                try:
                    save_cv_report(report, args.output)
                except FileExistsError:
                    write("Comparison not saved: the output path already exists. Choose a new filename.")
                    return 1
                except OSError:
                    write("Comparison could not be saved. Check permissions, space and support for atomic links.")
                    return 1
                write("Comparison saved locally.")
            else:
                write("Comparison not saved.")
        return 1 if store_failed else 0
    except (JobError, DocumentError, AnalysisError, storage.StorageError) as error:
        write(str(error))
    except (OSError, sqlite3.Error):
        write("Local comparison operation failed. Check the database/file path and permissions.")
    return 1
