"""Azure Functions entry point — timer-triggered property pipeline."""
import logging

import azure.functions as func

from pipeline import run_once

app = func.FunctionApp()


# Daily at 08:00 UTC — one "daily brief" digest of the day's new matches.
@app.timer_trigger(schedule="0 0 8 * * *", arg_name="timer", run_on_startup=False)
async def poll_listings(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("timer past due — running anyway")
    fresh = await run_once(notify_results=True)
    logging.info("homeScout: %d new/changed listing(s) this run", len(fresh))
