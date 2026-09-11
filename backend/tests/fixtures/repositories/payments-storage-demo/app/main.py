from fastapi import FastAPI

app = FastAPI(title="Payments & Storage Demo", version="1.0.0")


@app.post("/payments/checkout")
def create_checkout():
    return {"status": "created"}


@app.get("/payments/{payment_id}")
def get_payment(payment_id: str):
    return {"id": payment_id}


@app.post("/files/upload")
def upload_file():
    return {"file": "uploaded"}


@app.get("/files/{file_id}")
def download_file(file_id: str):
    return {"file": file_id}
