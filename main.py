from src.server import app
from src.assets import JsonData
import src.accessories.logger as logger
import uvicorn

if __name__ == '__main__':
    logger.setup_logging()
    JsonData.init()
    uvicorn.run(app, host="0.0.0.0", port=9000, log_config=logger.LOG_CONFIG)
