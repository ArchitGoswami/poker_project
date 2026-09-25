import uvicorn

if __name__ == "__main__":
    print("the poker project is at http://127.0.0.1:8765")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765)
