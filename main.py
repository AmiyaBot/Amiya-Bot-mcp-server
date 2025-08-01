from src.server import app
from src.assets import JsonData
import uvicorn

if __name__ == '__main__':

    JsonData.init()

    uvicorn.run(app, host="0.0.0.0", port=9000)
