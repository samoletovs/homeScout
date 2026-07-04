"""Azure Functions entry point — timer-triggered property pipeline."""
import logging

import azure.functions as func

from pipeline import run_once

app = func.FunctionApp()


# Every 30 minutes (ss.lv RSS ttl is ~5 min; 30 min is polite and sufficient).
@app.timer_trigger(schedule="0 */30 * * * *", arg_name="timer", run_on_startup=False)
async def poll_listings(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("timer past due — running anyway")
    fresh = await run_once(notify_results=True)
    logging.info("homeScout: %d new/changed listing(s) this run", len(fresh))
