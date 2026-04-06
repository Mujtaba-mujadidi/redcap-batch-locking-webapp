from fastapi import FastAPI

app = FastAPI(title="REDCap Batch Locking", version="0.0.1")


@app.get("/")
def hello():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    return {"status": "ok"}
