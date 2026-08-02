"""Azure Functions entry point — timer-triggered property pipeline."""
import logging

import azure.functions as func

from pipeline import run_once

app = func.FunctionApp()

# httpx logs the full request URL at INFO, and the Telegram API carries the bot token in
# the path — which writes the live token into Application Insights, where it is retained.
# No request detail here is worth a leaked credential.
logging.getLogger("httpx").setLevel(logging.WARNING)


# Daily at 12:00 UTC — one "daily brief" digest of the day's new matches.
@app.timer_trigger(schedule="0 0 12 * * *", arg_name="timer", run_on_startup=False)
async def poll_listings(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("timer past due — running anyway")
    fresh = await run_once(notify_results=True)
    logging.info("homeScout: %d new/changed listing(s) this run", len(fresh))


# Family feedback intake — the agentMode Telegram gate POSTs 👍/👎 + comments here.
# Comments arrive in the family's language; homeScout translates them to English for
# storage and folds them into the learned taste that steers the adviser. Function-key
# protected: the gate holds the URL (incl. ?code=) as a secret.
@app.route(route="feedback", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def feedback_intake(req: func.HttpRequest) -> func.HttpResponse:
    import json

    from feedback import record

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            '{"ok": false, "error": "invalid json"}',
            mimetype="application/json", status_code=400,
        )
    result = await record(body)
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        mimetype="application/json",
        status_code=200 if result.get("ok") else 400,
    )
