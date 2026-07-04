"""Azure Functions entry point — timer-triggered property pipeline."""
import logging

import azure.functions as func

from pipeline import run_once

app = func.FunctionApp()


# Every 30 minutes. Adjust the NCRONTAB expression as needed.
@app.timer_trigger(schedule="0 */30 * * * *", arg_name="timer", run_on_startup=False)
def poll_listings(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("timer past due — running anyway")
    scored = run_once(notify_results=True)
    logging.info("pipeline produced %d scored listings", len(scored))
