from fastapi import FastAPI

app = FastAPI(title='Heraclitus SaaS Portal')

@app.get('/')
def read_root():
    return {'status': 'Heraclitus Operational', 'version': '2026.1'}
