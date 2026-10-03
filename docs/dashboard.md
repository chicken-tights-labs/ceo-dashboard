# CEO Dashboard - Live Kanban UI

## Files
- `src/dashboard_server.py` — FastAPI server (port 8081)
- `src/templates/dashboard.html` — Kanban board view
- `src/static/dashboard.css` — Dashboard styles

## Running
```bash
pip install fastapi jinja2 uvicorn
uvicorn src.dashboard_server:app --host 127.0.0.1 --port 8081
```

## NGINX Route
```nginx
location /ceo-dashboard/ {
    proxy_pass http://127.0.0.1:8081/;
}
```
