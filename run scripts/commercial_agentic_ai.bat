@echo off
setlocal

start "commercial_agentic_ai" /D "C:\source\python\commercial_agentic_ai" cmd /K ^
  "poetry run uvicorn commercial_agentic_ai.asgi:app --host 0.0.0.0 --port 8000 --reload"

endlocal
