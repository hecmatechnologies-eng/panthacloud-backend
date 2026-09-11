from fastapi import FastAPI

app = FastAPI(title="Demo API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/items")
def create_item():
    return {"item": "created"}
